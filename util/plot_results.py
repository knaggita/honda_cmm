import argparse
import matplotlib.pyplot as plt
import numpy as np
from util import util
import sys
from util.util import Result
from learning.test_model import SearchResult, SampleResult
from actions.policies import PrismaticParams, RevoluteParams, get_policy_params

class PlotFunc(object):

    @staticmethod
    def description():
        return 'No description for PlotFunc: ' + self.__name__

    def plot(self, figure_num, plot_data):
        self._plot(plot_data)

class DoorRadiusMotion(PlotFunc):

    @staticmethod
    def description():
        return 'Plot the door radius versus the joint motion'

    def _plot(self, plot_data):
        for data_point in plot_data:
            if data_point.mechanism_params.type == 'Door':
                plt.plot(data_point.mechanism_params.params.door_size[0], data_point.motion, 'b.')
        plt.xlabel('Door Radius')
        plt.ylabel('Motion of Handle')
        plt.title('Motion of Doors')

class SliderRangeMotion(PlotFunc):

    @staticmethod
    def description():
        return 'Plot the slider range versus the joint motion'

    def _plot(self, plot_data):
        for data_point in plot_data:
            if data_point.mechanism_params.type == 'Slider':
                plt.plot(data_point.mechanism_params.params.range, data_point.motion, 'b.')
        plt.xlabel('Slider Range')
        plt.ylabel('Motion of Handle')
        plt.title('Motion of Sliders')

class DoorRadiusWR(PlotFunc):

    @staticmethod
    def description():
        return 'Plot the door radius versus the % of waypoints reached'

    def _plot(self, plot_data):
        for data_point in plot_data:
            if data_point.mechanism_params.type == 'Door':
                plt.plot(data_point.mechanism_params.params.door_size[0], data_point.waypoints_reached, 'b.')
        plt.xlabel('Door Radius')
        plt.ylabel('Percentage of Trajectory Waypoints Reached')
        plt.title('Waypoints Reached by Door')

class SliderRangeWR(PlotFunc):

    @staticmethod
    def description():
        return 'Plot the slider range versus the % of waypoints reached'

    def _plot(self, plot_data):
        for data_point in plot_data:
            if data_point.mechanism_params.type == 'Slider':
                plt.plot(data_point.mechanism_params.params.range, data_point.waypoints_reached, 'b.')
        plt.xlabel('Slider Range')
        plt.ylabel('Percentage of Trajectory Waypoints Reached')
        plt.title('Slider Range vs Waypoints Reached')

class SliderAxisMotion(PlotFunc):

    @staticmethod
    def description():
        return 'Plot the slider axis versus the joint_motion'

    def _plot(self, plot_data):
        for data_point in plot_data:
            if data_point.mechanism_params.type == 'Slider':
                angle = np.arccos(data_point.mechanism_params.params.axis[0])
                plt.plot(angle, data_point.motion, 'b.')
        plt.xlabel('Slider Axis Angle')
        plt.ylabel('Motion of Handle')
        plt.title('Motion of Handle')

class SliderAxisWR(PlotFunc):

    @staticmethod
    def description():
        return 'Plot the slider axis versus the % of waypoints reached'

    def _plot(self, plot_data):
        for data_point in plot_data:
            if data_point.mechanism_params.type == 'Slider':
                angle = np.arccos(data_point.mechanism_params.params.axis[0])
                plt.plot(angle, data_point.waypoints_reached, 'b.')
        plt.xlabel('Slider Axis Angle')
        plt.ylabel('Percentage of Trajectory Waypoints Reached')
        plt.title('Slider Angle vs Waypoints Reached')

class WRKD(PlotFunc):

    @staticmethod
    def description():
        return 'Plot a heatmap of the % waypoints reached for varying k and d values'

    def _plot(self, plot_data):
        fig0, ax0 = plt.subplots()
        fig1, ax1 = plt.subplots()
        cm = plt.cm.get_cmap('copper')

        for data_point in plot_data:
            wr = data_point.waypoints_reached
            a = ax0.scatter([data_point.control_params.k[0]], [data_point.control_params.d[0]], \
                                cmap=cm, c=[wr], s=2, vmin=0, vmax=1) # s is markersize
            b = ax1.scatter([data_point.control_params.k[1]], [data_point.control_params.d[1]], \
                                cmap=cm, c=[wr], s=2, vmin=0, vmax=1)

        ks = np.power(10.,np.linspace(-5, 5,1000))
        gripper_mass = 1.5
        ds_critically_damped = np.sqrt(4*gripper_mass*ks)
        ax0.plot(ks, ds_critically_damped, label='critically damped')

        ax0.set_xlabel('Linear K')
        ax0.set_ylabel('Linear D')
        ax0.set_title('Time before Reached Goal or Timeout for Doors')
        ax0.legend()

        ax1.set_xlabel('Angular K')
        ax1.set_ylabel('Angular D')
        ax1.set_title('Time before Reached Goal or Timeout for Doors')

        ax0.set_yscale('log')
        ax0.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_xscale('log')

        #ax0.set_xlim(*np.power(10.,k_lin_range))
        #ax0.set_ylim(*np.power(10.,d_lin_range))
        #ax1.set_xlim(*np.power(10.,k_rot_range))
        #ax1.set_ylim(*np.power(10.,d_rot_range))

        fig0.colorbar(a)
        fig1.colorbar(b)

class MechanismMotion(PlotFunc):

    @staticmethod
    def description():
        return 'Plot a histogram of the motion generated for each (mechanism type, policy tried) in a dataset'

    def _plot(self, plot_data):
        plt_cont = input('Only plot motion if gripper touching handle at end of execution? [y/n] then [ENTER]')
        data_hist = {}
        for data_point in plot_data:
            key = data_point.mechanism_params.type + ', ' +  data_point.policy_params.type
            if plt_cont == 'n' or (plt_cont == 'y' and data_point.pose_joint_world_final):
                if key in data_hist:
                    data_hist[key].append(data_point.motion)
                else:
                    data_hist[key] = []

        colors = {'Slider, Prismatic': 'blue', 'Slider, Revolute': 'orange', \
                    'Door, Prismatic': 'green', 'Door, Revolute': 'red'}
        ordered_colors = [colors[key] for key in data_hist.keys()]
        plt.hist(data_hist.values(), 20, histtype='bar', label=data_hist.keys(), color=ordered_colors)
        plt.xlabel('Motion')
        plt.ylabel('Frequency')
        plt.title('Motion of Mechanisms')
        plt.legend()

class SearchData(PlotFunc):

    @staticmethod
    def description():
        return 'Plot the predicted motion for mechanisms in search results dataset'

    def _plot(self, plot_data):
        for mechanism_samples in plot_data:
            self._plot_single_mechanism(mechanism_samples)

    def _plot_single_mechanism(self, results):
        fig = plt.figure()
        # set up big subplots and turn of axis lines and ticks
        ax = fig.add_subplot(111)
        ax_left = fig.add_subplot(121)
        ax_right = fig.add_subplot(122)
        ax.spines['top'].set_color('none')
        ax.spines['bottom'].set_color('none')
        ax.spines['left'].set_color('none')
        ax.spines['right'].set_color('none')
        ax.tick_params(labelcolor='w', top=False, bottom=False, left=False, right=False)
        ax_left.spines['top'].set_color('none')
        ax_left.spines['bottom'].set_color('none')
        ax_left.spines['left'].set_color('none')
        ax_left.spines['right'].set_color('none')
        ax_left.tick_params(labelcolor='w', top=False, bottom=False, left=False, right=False)
        ax_right.spines['top'].set_color('none')
        ax_right.spines['bottom'].set_color('none')
        ax_right.spines['left'].set_color('none')
        ax_right.spines['right'].set_color('none')
        ax_right.tick_params(labelcolor='w', top=False, bottom=False, left=False, right=False)

        # fill in small subplots
        ax00 = fig.add_subplot(421)
        ax10 = fig.add_subplot(423)
        ax20 = fig.add_subplot(425)
        ax30 = fig.add_subplot(427)
        ax01 = fig.add_subplot(422)
        ax11 = fig.add_subplot(424)
        ax21 = fig.add_subplot(426)
        ax31 = fig.add_subplot(428)

        # turn of axes for missing plot
        ax30.spines['top'].set_color('none')
        ax30.spines['bottom'].set_color('none')
        ax30.spines['left'].set_color('none')
        ax30.spines['right'].set_color('none')
        ax30.tick_params(labelcolor='w', top=False, bottom=False, left=False, right=False)

        for sample in results.samples:
            plot_data = get_policy_params(sample.policy)
            if sample.policy.type == 'Prismatic':
                ax00.plot(sample.config_goal, sample.pred_motion, '.k')
                ax10.plot(plot_data[0], sample.pred_motion, '.k')
                ax20.plot(plot_data[1], sample.pred_motion, '.k')
            if sample.policy.type == 'Revolute':
                ax01.plot(sample.config_goal, sample.pred_motion, '.k')
                ax11.plot(plot_data[0], sample.pred_motion, '.k')
                ax21.plot(plot_data[1], sample.pred_motion, '.k')
                ax31.plot(plot_data[2], sample.pred_motion, '.k')

        # plot initial search sample
        ys = [0,.11]
        if results.start_sample.policy.type == 'Prismatic':
            plot_data = get_policy_params(results.start_sample.policy)
            ax00.plot([results.start_sample.config_goal, results.start_sample.config_goal], ys, 'r')
            ax10.plot([plot_data[0], plot_data[0]], ys, 'r')
            ax20.plot([plot_data[1], plot_data[1]], ys, 'r')
        if results.start_sample.policy.type == 'Revolute':
            plot_data = get_policy_params(results.start_sample.policy)
            ax01.plot([results.start_sample.config_goal, results.start_sample.config_goal], ys, 'r')
            ax11.plot([plot_data[0], plot_data[0]], ys, 'r')
            ax21.plot([plot_data[1], plot_data[1]], ys, 'r')
            ax31.plot([plot_data[2], plot_data[2]], ys, 'r')

        # plot final search sample
        if results.end_sample.policy.type == 'Prismatic':
            plot_data = get_policy_params(results.end_sample.policy)
            ax00.plot([results.end_sample.config_goal, results.end_sample.config_goal], ys, 'g--')
            ax10.plot([plot_data[0], plot_data[0]], ys, 'g--')
            ax20.plot([plot_data[1], plot_data[1]], ys, 'g--')
        if results.end_sample.policy.type == 'Revolute':
            plot_data = get_policy_params(results.end_sample.policy)
            ax01.plot([results.end_sample.config_goal, results.end_sample.config_goal], ys, 'g--')
            ax11.plot([plot_data[0], plot_data[0]], ys, 'g--')
            ax21.plot([plot_data[1], plot_data[1]], ys, 'g--')
            ax31.plot([plot_data[2], plot_data[2]], ys, 'g--')

        # show image of mechanism is one of the subplots
        ax30.imshow(results.image_data[2])

        ax_left.set_title('Prismatic Policies')
        ax_left.set_ylabel('Predicted Motion')
        ax_right.set_title('Revolute Policies')
        ax_right.set_ylabel('Predicted Motion')
        ax00.set_xlabel('Goal Config')
        ax10.set_xlabel('Roll')
        ax20.set_xlabel('Pitch')
        ax01.set_xlabel('Goal Config')
        ax11.set_xlabel('Radius')
        ax21.set_xlabel('Roll')
        ax31.set_xlabel('Pitch')

def print_stats(data):
    stats = {}
    for data_point in data:
        mech_type = data_point.mechanism_params.type
        policy_type = data_point.policy_params.type
        key = (mech_type, policy_type)
        if key not in stats:
            stats[key] = 1
        else:
            stats[key] += 1
    print('Stats on the dataset')
    for (key, val) in stats.items():
        sys.stdout.write('  %s mech, %s policy: %i\n' % (*key, val))

def plot_results(file_name):
    data = util.read_from_file(file_name)
    if type(data[0]) == Result:
        print_stats(data)

    plot_funcs = PlotFunc.__subclasses__()
    for (i, func) in enumerate(plot_funcs):
        print(i, ':', func.description())
    plot_nums = input('Above are the possible plots, type in the numbers of the plots you would like to visualize, eg. 1, 3, 4 [ENTER]\n')
    plot_nums = list(map(int, plot_nums.strip('[]').split(',')))

    plt.ion()
    for plot_num in plot_nums:
        plot_func = plot_funcs[plot_num]()
        plot_func.plot(plot_num, data)
    plt.show()
    input('hit [ENTER] to close plots')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--fname', type=str, required=True) # give filename (without .pickle)
    args = parser.parse_args()

    if args.debug:
        import pdb; pdb.set_trace()

    plot_results(args.fname)