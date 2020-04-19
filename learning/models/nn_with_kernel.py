import torch
import torch.nn as nn
import torch.nn.functional as F
from learning.modules.policy_encoder import PolicyEncoder
from learning.modules.image_encoder_spatialsoftmax import ImageEncoder as SpatialEncoder
from learning.modules.image_encoder import ImageEncoder as CNNEncoder
from learning.models.nn_disp_pol_vis import DistanceRegressor
from learning.dataloaders import setup_data_loaders, parse_pickle_file
import gpytorch
from gpytorch.kernels import GridInterpolationKernel, ScaleKernel, RBFKernel
from utils.util import load_model, read_from_file


class FeatureExtractor(nn.Module):
    def __init__(self, pretrained_nn_path):
        super(FeatureExtractor, self).__init__()
        self.pretrained_model = load_model(model_fname=pretrained_nn_path,
                                           hdim=16)
        
    def forward(self, policy_type, im, theta):
        policy_type = 1
        if policy_type == 0:
            policy_type = 'Prismatic'
        else:
            policy_type = 'Revolute'
        pol = self.pretrained_model.policy_modules[policy_type].forward(theta)
        im, points = self.pretrained_model.image_module(im)

        x = torch.cat([pol, im], dim=1)
        x = F.relu(self.pretrained_model.fc1(x))
        x = F.relu(self.pretrained_model.fc2(x))
        return x


class DistanceGP(gpytorch.models.ExactGP):
    def __init__(self, train_x, train_y, likelihood):
        super(DistanceGP, self).__init__(train_x, train_y, likelihood)
        num_gp_dims = 2 
        # Create a mean function. 
        # Note: Should this be the pretrained NN prediction?
        self.mean_module = gpytorch.means.ConstantMean()
        # Note: Should probably make kernel dims smaller by adding a learned Linear layer on top?
        self.covar_module = GridInterpolationKernel(
                                ScaleKernel(RBFKernel(ard_num_dims=num_gp_dims)),
                                num_dims=num_gp_dims, grid_size=500)
        self.lin = nn.Linear(32, num_gp_dims)

    def forward(self, x):
        x = self.lin(x)
        x = x - x.min(0)[0]
        x = 2*(x/x.max(0)[0])-1
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        return gpytorch.distributions.MultivariateNormal(mean_x, covar_x)


def convert_training_data(train_set):
    """ GPyTorch requires the data in as two tensors: NxD, N
    """
    policies = torch.stack(train_set.dataset.tensors)
    ims = torch.stack(train_set.dataset.images)
    ys = torch.tensor(train_set.dataset.ys)
    print('Policy:', type(policies), policies.shape)
    print('Im:', type(ims), ims.shape)
    print('Y:', type(ys), ys.shape)
    xs = torch.cat([policies, 
                    ims.reshape(ims.shape[0], ims.shape[1]*ims.shape[2]*ims.shape[3])], dim=1)

    return xs, ys

def extract_feature_dataset(dataset, extractor, use_cuda=False):
    """ First extract the features from the dataset."""
    features, ys = [], []
    for policy_type, theta, im, y, _ in dataset:
        if use_cuda:
            theta = theta.cuda()
            im = im.cuda()
            y = y.cuda()
        feats = extractor(policy_type, im, theta)
        features.append(feats.detach())
        ys.append(y)
    return torch.cat(features, dim=0), torch.cat(ys, dim=0).squeeze()


if __name__ == '__main__':
    CUDA = True
    #  Load dataset.
    raw_results = read_from_file('/home/michael/workspace/honda_cmm/data/doors_gpucb_100L_100M_set0.pickle')
    results = [bb[::10] for bb in raw_results]  # For now just grab every 10th interaction with each bbb.
    results = [item for sublist in results for item in sublist]

    data = parse_pickle_file(results)
    train_set, val_set, _ = setup_data_loaders(data=data, batch_size=16)

    extractor = FeatureExtractor(pretrained_nn_path='/home/michael/workspace/honda_cmm/pretrained_models/doors/model_100L_100M.pt')
    if CUDA:
        extractor.cuda()
    print('Extracting Features')
    train_x, train_y = extract_feature_dataset(train_set, extractor, use_cuda=CUDA)
    print('Features Extracted')
    print(train_x.shape, train_y.shape)
    val_x, val_y = extract_feature_dataset(val_set, extractor, use_cuda=CUDA)
    del extractor, train_set, val_set
    print('Data Size:', train_x.shape, train_y.shape)
    print(train_x.size(0), train_y.size(0))
    likelihood = gpytorch.likelihoods.GaussianLikelihood()
    gp = DistanceGP(train_x=train_x,
                    train_y=train_y,
                    likelihood=likelihood)
    if CUDA:
        likelihood = likelihood.cuda()
        gp = gp.cuda()
    gp.train()
    likelihood.train()
    optimizer = torch.optim.Adam([{'params': gp.covar_module.parameters()},
                                  {'params': gp.lin.parameters()}], lr=0.1)
    mll = gpytorch.mlls.ExactMarginalLogLikelihood(likelihood, gp)
    
    for _ in range(100):
        optimizer.zero_grad()
        output = gp(train_x)
        loss = -mll(output, train_y)
        loss.backward()
        optimizer.step()

        print(loss.item(), gp.likelihood.noise.item())
    gp.eval()
    print('Val Predictions')
    for ix in range(0, 10):
        pred = gp(val_x[ix:ix+1, :])
        print(pred.mean.cpu().detach().numpy(), 
              pred.confidence_region()[0].cpu().detach().numpy(),
              pred.confidence_region()[1].cpu().detach().numpy(),
              val_y[ix])

    print('Train Predictions')
    for ix in range(0, 10):
        pred = gp(train_x[ix:ix+1, :])
        print(pred.mean.cpu().detach().numpy(), 
              pred.confidence_region()[0].cpu().detach().numpy(),
              pred.confidence_region()[1].cpu().detach().numpy(), 
              train_y[ix])

