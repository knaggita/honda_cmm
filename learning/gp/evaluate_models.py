import pickle
import argparse
import os
import numpy as np
import re
from learning.gp.explore_single_bb import create_single_bb_gpucb_dataset, GPOptimizer
from utils import util, setup_pybullet
from gen.generate_policy_data import get_bb_dataset

SUCCESS_REGRET = 0.05

def get_models(L, models_path):
    all_files = os.walk(models_path)
    models = []
    for root, subdir, files in all_files:
        for file in files:
            if (file[-3:] == '.pt') and ('_'+str(L)+'L_' in file):
                full_path = root+'/'+file
                models.append(full_path)
    return models

# regret_results file the same as above, but instead of lists of regret values
# for each BB and model, it is a list of the number of steps it took GPUCB to
# find successful parameters

def evaluate_models(n_bbs, args, use_cuda=False):
    bb_data = get_bb_dataset(args.bb_fname, n_bbs, args.mech_types, 1, args.urdf_num)

    all_results = {}
    for L in range(args.Ls[0], args.Ls[1]+1, args.Ls[2]):
        models = get_models(L, args.models_path)
        all_L_results = {}
        for model in models:
            all_model_test_steps = []
            for ix, bb_result in enumerate(bb_data[:n_bbs]):
                if args.debug:
                    print('BusyBox', ix)
                dataset, gps, steps = create_single_bb_gpucb_dataset(bb_result[0],
                                                model,
                                                args.plot,
                                                args,
                                                ix,
                                                success_regret=SUCCESS_REGRET,
                                                plot_dir_prefix='L'+str(L),)
                all_model_test_steps.append(steps)
                if args.debug:
                    print('Test Steps   :', steps)
            if args.debug:
                print('Results')
                # print('Average Regret:', np.mean(avg_regrets))
                print('Final Avg Steps  :', np.mean(all_model_test_steps))
            all_L_results[model] = all_model_test_steps
        if len(models) > 0:
            all_results[L] = all_L_results
    util.write_to_file('regret_results_%s_%dN_%s.pickle' % (args.type, n_bbs, args.mech_types[0]),
                       all_results,
                       verbose=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--n-gp-samples',
        type=int,
        default=1000,
        help='number of samples to use when fitting a GP to data')
    parser.add_argument(
        '--T',
        type=int,
        help='number of interactions within a single BusyBox during evaluation time')
    parser.add_argument(
        '--N',
        type=int,
        help='number of BusyBoxes to interact with during evaluation time')
    parser.add_argument(
        '--type',
        type=str,
        required=True,
        help='evaluation type in [random, gpucb, active, systematic]')
    parser.add_argument(
        '--urdf-num',
        default=0,
        help='number to append to generated urdf files. Use if generating multiple datasets simultaneously.')
    parser.add_argument(
        '--bb-fname',
        default='',
        help='path to file of BusyBoxes to interact with')
    parser.add_argument(
        '--plot',
        action='store_true',
        help='use to generate polar plots durin GP-UCB interactions')
    parser.add_argument(
        '--debug',
        action='store_true',
        help='use to enter debug mode')
    parser.add_argument(
        '--hdim',
        type=int,
        default=16,
        help='hdim of supplied model(s), used to load model file')
    parser.add_argument(
        '--models-path',
        help='path to model files')
    parser.add_argument(
        '--Ls',
        nargs=3,
        type=int,
        help='min max step of Ls')
    parser.add_argument('--mech-types', nargs='+', default=['slider'], type=str)
    args = parser.parse_args()

    if args.debug:
        import pdb; pdb.set_trace()

    evaluate_models(args.N, args)
