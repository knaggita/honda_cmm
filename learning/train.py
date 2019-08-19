import argparse
import numpy as np
import torch
from learning.models.nn_disp_pol_vis import DistanceRegressor as NNPolVis
from learning.models.nn_disp_pol_mech import DistanceRegressor as NNPolMech
from learning.dataloaders import setup_data_loaders
import learning.viz as viz
from collections import namedtuple
from util import util
from torch.utils.tensorboard import SummaryWriter
from collections import OrderedDict
torch.backends.cudnn.enabled = True

RunData = namedtuple('RunData', 'hdim batch_size run_num max_epoch best_epoch best_val_error')
name_lookup = {'Prismatic': 0, 'Revolute': 1}

def train_eval(args, n_train, data_path, hdim, batch_size, pviz, plot_fname, writer):
    # always use the validation and test set from the random dataset
    _, val_set, test_set = setup_data_loaders(fname=args.random_data_path,
                                                      batch_size=batch_size,
                                                      small_train=n_train)

    # Load data
    train_set, _, _ = setup_data_loaders(fname=data_path,
                                                      batch_size=batch_size,
                                                      small_train=n_train)

    # Setup Model (TODO: Update the correct policy dims)
    net = NNPolVis(policy_names=['Prismatic', 'Revolute'],
                   policy_dims=[2, 12],
                   hdim=hdim,
                   im_h=53,  # 154,
                   im_w=115,  # 205,
                   kernel_size=3,
                   image_encoder=args.image_encoder)
    # net = NNPolMech(policy_names=['Prismatic'],
    #                 policy_dims=[2],
    #                 hdim=hdim,
    #                 mech_dims=2)
    print(sum(p.numel() for p in net.parameters() if p.requires_grad))

    if args.use_cuda:
        net = net.cuda()

    loss_fn = torch.nn.MSELoss()
    optim = torch.optim.Adam(net.parameters())

    # Add the graph to TensorBoard viz,
    k, x, q, im, y, _ = train_set.dataset[0]
    pol = torch.Tensor([name_lookup[k]])
    if args.use_cuda:
        x = x.cuda().unsqueeze(0)
        q = q.cuda().unsqueeze(0)
        im = im.cuda().unsqueeze(0)
        pol = pol.cuda()

    best_val = 1000
    # Training loop.
    val_errors = OrderedDict()
    for ex in range(1, args.n_epochs+1):
        train_losses = []
        net.train()
        for bx, (k, x, q, im, y, _) in enumerate(train_set):
            pol = name_lookup[k[0]]
            if args.use_cuda:
                x = x.cuda()
                q = q.cuda()
                im = im.cuda()
                y = y.cuda()
            optim.zero_grad()
            yhat = net.forward(pol, x, q, im)

            loss = loss_fn(yhat, y)
            loss.backward()

            optim.step()

            train_losses.append(loss.item())

        print('[Epoch {}] - Training Loss: {}'.format(ex, np.mean(train_losses)))

        if ex % args.val_freq == 0:
            val_losses = []
            net.eval()

            ys, yhats, types = [], [], []
            for bx, (k, x, q, im, y, _) in enumerate(val_set):
                pol = torch.Tensor([name_lookup[k[0]]])
                if args.use_cuda:
                    x = x.cuda()
                    q = q.cuda()
                    im = im.cuda()
                    y = y.cuda()

                yhat = net.forward(pol, x, q, im)

                loss = loss_fn(yhat, y)
                val_losses.append(loss.item())

                types += k
                if args.use_cuda:
                    y = y.cpu()
                    yhat = yhat.cpu()
                ys += y.numpy().tolist()
                yhats += yhat.detach().numpy().tolist()

            curr_val = np.mean(val_losses)
            val_errors[ex] = curr_val
            plot_val_error(val_errors, 'epoch', 'val error '+plot_fname, writer, False)

            print('[Epoch {}] - Validation Loss: {}'.format(ex, curr_val))
            if curr_val < best_val:
                best_val = curr_val
                best_epoch = ex

                # save model
                model_fname = plot_fname+'_epoch_'+str(best_epoch)
                full_path = 'torch_models/'+model_fname+'.pt'
                torch.save(net.state_dict(), full_path)

                # save plot of prediction error
                if pviz:
                    viz.plot_y_yhat(ys, yhats, types, ex, plot_fname, title='PolVis')
    return val_errors, best_epoch

def plot_val_error(val_errors, type, plot_fname, writer, viz=False):
    import matplotlib.pyplot as plt
    fig = plt.figure()
    plt.xlabel(type)
    plt.ylabel('Val MSE')
    if isinstance(list(val_errors.keys())[0], int):
        plt.plot(list(val_errors.keys()), list(val_errors.values()))
    else:
        for file in val_errors.keys():
            plt.plot(list(val_errors[file].keys()), list(val_errors[file].values()), label=file)
    plt.legend()
    writer.add_figure(plot_fname, fig)
    if viz:
        plt.show()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-size', type=int, help='Batch size to use for training.')
    parser.add_argument('--hdim', type=int, help='Hidden dimensions for the neural nets.')
    parser.add_argument('--n-epochs', type=int, default=10)
    parser.add_argument('--val-freq', type=int, default=5)
    parser.add_argument('--mode', choices=['ntrain', 'normal'], default='normal')
    parser.add_argument('--use-cuda', default=False, action='store_true')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--random-data-path', type=str, required=True) # always needed for validation
    parser.add_argument('--active-data-path', type=str)
    parser.add_argument('--model-prefix', type=str, default='model')
    # in normal mode: if 0 use all samples in dataset, else use ntrain number of samples
    # in ntrain mode: must be the max number of samples you want to train with
    parser.add_argument('--n-train', type=int, default=0)
    parser.add_argument('--step', type=int, default=1000)
    parser.add_argument('--image-encoder', type=str, default='spatial', choices=['spatial', 'cnn'])
    parser.add_argument('--n-runs', type=int, default=1)
    args = parser.parse_args()

    if args.debug:
        import pdb; pdb.set_trace()

    # if hdim and batch_size given as args then use them, otherwise test a list of them
    if args.hdim:
        hdims = [args.hdim]
    else:
        hdims = [16, 32]
    if args.batch_size:
        batch_sizes = [args.batch_size]
    else:
        batch_sizes = [16, 32]

    # get list of data_paths to try
    data_tups = [('random', args.random_data_path)]
    if args.active_data_path is not None:
        data_tups = [('active', args.active_data_path)] + data_tups

    writer = SummaryWriter()
    if args.mode == 'normal':
        for data_tup in data_tups:
            run_data = []
            for n in range(args.n_runs):
                for hdim in hdims:
                    for batch_size in batch_sizes:
                        plot_fname = args.model_prefix+'_nrun_'+str(n)+'_'+str(data_tup[0])
                        val_errors, best_epoch = train_eval(args, 0, data_tup[1], hdim, batch_size, False, plot_fname, writer)
                        run_data += [RunData(hdim, batch_size, n, args.n_epochs, best_epoch, min(val_errors.keys()))]
            util.write_to_file(plot_fname+'_results', run_data)
    elif args.mode == 'ntrain':
        ns = range(args.step, args.n_train+1, args.step)
        val_errors = OrderedDict()
        for n_train in ns:
            for data_tup in data_tups:
                if not data_tup[0] in val_errors:
                    val_errors[data_tup[0]] = OrderedDict()
                plot_fname = 'data_'+data_tup[0]+'_ntrain_'+str(n_train)
                all_vals_epochs, best_epoch = train_eval(args, n_train, data_tup[1], args.hdim, args.batch_size, False, plot_fname, writer)
                val_errors[data_tup[0]][n_train] = all_vals_epochs[best_epoch]
                plot_val_error(val_errors, 'n train', 'ntrain error', writer)
