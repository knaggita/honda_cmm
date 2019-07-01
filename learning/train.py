import argparse
import numpy as np
import torch
from learning.nn_disp_pol import DistanceRegressor as NNPol
from learning.nn_disp_pol_vis import DistanceRegressor as NNPolVis
from learning.dataloaders import setup_data_loaders
import learning.viz as viz


def train_eval(args, n_train, data_file_name, model_file_name, pviz, use_cuda):
    # Load data
    train_set, val_set, test_set = setup_data_loaders(fname=data_file_name,
                                                      batch_size=args.batch_size,
                                                      small_train=n_train)

    # Setup Model (TODO: Update the correct policy dims)
    if args.model == 'pol':
        net = NNPol(policy_names=['Prismatic', 'Revolute'],
                    policy_dims=[10, 14],
                    hdim=args.hdim)
    else:
        net = NNPolVis(policy_names=['Prismatic', 'Revolute'],
                       policy_dims=[10, 14],
                       hdim=args.hdim,
                       im_h=154,
                       im_w=205,
                       kernel_size=5)
    if use_cuda:
        net = net.cuda()

    loss_fn = torch.nn.MSELoss()
    optim = torch.optim.Adam(net.parameters())

    best_val = 1000
    # Training loop.
    for ex in range(args.n_epochs):
        train_losses = []
        for bx, (k, x, q, im, y) in enumerate(train_set):
            if use_cuda:
                x = x.cuda()
                q = q.cuda()
                im = im.cuda()
                y = y.cuda()

            optim.zero_grad()
            yhat = net.forward(k[0], x, q, im)

            loss = loss_fn(yhat, y)
            loss.backward()

            optim.step()

            train_losses.append(loss.item())

        print('[Epoch {}] - Training Loss: {}'.format(ex, np.mean(train_losses)))

        if ex % args.val_freq == 0:
            val_losses = []

            ys, yhats, types = [], [], []
            for bx, (k, x, q, im, y) in enumerate(val_set):
                if use_cuda:
                    x = x.cuda()
                    q = q.cuda()
                    im = im.cuda()
                    y = y.cuda()

                yhat = net.forward(k[0], x, q, im)
                loss = loss_fn(yhat, y)

                val_losses.append(loss.item())

                types += k
                if use_cuda:
                    y = y.cpu()
                    yhat = yhat.cpu()
                ys += y.numpy().tolist()
                yhats += yhat.detach().numpy().tolist()

            if pviz:
                viz.plot_y_yhat(ys, yhats, types, title='ImageOnly')

            print('[Epoch {}] - Validation Loss: {}'.format(ex, np.mean(val_losses)))
            if np.mean(val_losses) < best_val:
                best_val = np.mean(val_losses)
        torch.save(net.state_dict(), model_file_name)
    return best_val


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-size', type=int, default=32, help='Batch size to use for training.')
    parser.add_argument('--hdim', type=int, default=16, help='Hidden dimensions for the neural nets.')
    parser.add_argument('--n-epochs', type=int, default=10)
    parser.add_argument('--val-freq', type=int, default=5)
    parser.add_argument('--mode', choices=['ntrain', 'normal'], default='normal')
    parser.add_argument('--model', choices=['pol', 'polvis'], default='pol')
    parser.add_argument('--use-cuda', default=False, action='store_true')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--data-fname', type=str)
    parser.add_argument('--model-fname', type=str)
    args = parser.parse_args()

    if args.debug:
        import pdb; pdb.set_trace()

    data_file_name = args.data_fname + '.pickle'
    model_file_name = args.model_fname + '.pt'
    if args.mode == 'normal':
        train_eval(args, 0, data_file_name, model_file_name, pviz=True, use_cuda=args.use_cuda)
    elif args.mode == 'ntrain':
        vals = []
        ns = range(100, 1001, 100)
        for n in ns:
            best_val = train_eval(args, n, data_file_name, model_file_name, pviz=False, use_cuda=args.use_cuda)
            vals.append(best_val)
            print(n, best_val)

        import matplotlib.pyplot as plt
        plt.xlabel('n train')
        plt.ylabel('Val MSE')

        plt.plot(ns, vals)
        plt.show()
