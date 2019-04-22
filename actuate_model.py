import pybullet as p
import pybullet_data
import os
import time
import math
import json
import argparse
import numpy as np
from pyquaternion import Quaternion
from collections import defaultdict
from load_UBBDF import loadUBBDF
from gripper import Gripper
from util import transformation, vis_frame, Recorder
import plotting

# FOLDER = '/Users/carismoses/honda_cmm/'
FOLDER = '/home/mnosew/workspace/honda_cmm/'
def draw_prismatic(model):
    line_center = np.array([model['rigid_position.x'],
                            model['rigid_position.y'],
                            model['rigid_position.z']])
    axis = np.array([model['prismatic_dir.x'],
                     model['prismatic_dir.y'],
                     model['prismatic_dir.z']])
    lineFrom = (line_center + model['q_min[0]']*axis).tolist()
    lineTo = (line_center + model['q_max[0]']*axis).tolist()

    color = [1, 0, 1]

    p.addUserDebugLine(lineFromXYZ=lineFrom,
                       lineToXYZ=lineTo,
                       lineColorRGB=color,
                       lineWidth=2)
    p.addUserDebugText(text='pri',
                       textPosition=lineTo)

def draw_rigid(model):
    w = 0.025
    h = 0.1  # You can't see the lines if you draw them in the object so draw a bit above.
    line_center = np.array([model['rigid_position.x'],
                            model['rigid_position.y'],
                            model['rigid_position.z']])
    line1From = (line_center + np.array([-w, -w, h])).tolist()
    line1To = (line_center + np.array([w, w, h])).tolist()

    line2From = (line_center + np.array([-w, w, h])).tolist()
    line2To = (line_center + np.array([w, -w, h])).tolist()

    color = [1, 0, 1]
    p.addUserDebugLine(lineFromXYZ=line1From,
                       lineToXYZ=line1To,
                       lineColorRGB=color,
                       lineWidth=1)
    p.addUserDebugLine(lineFromXYZ=line2From,
                       lineToXYZ=line2To,
                       lineColorRGB=color,
                       lineWidth=1)
    p.addUserDebugLine(lineFromXYZ=line_center.tolist(),
                       lineToXYZ=(line_center + np.array([0, 0, h])).tolist(),
                       lineColorRGB=color,
                       lineWidth=1)

    p.addUserDebugText(text='rig',
                       textPosition=line1To)

def joint_to_point(q, rot_ax, rot_center, rot_radius):
    p0 = np.array([rot_radius, 0, 0])
    
    qq = Quaternion(axis=[0, 0, 1],
                    angle=-q)

    p0 = qq.rotate(p0)
    p0 = rot_ax.rotate(p0)
    p0 += rot_center
    return p0

def draw_revolute(model):
    rot_center = np.array([model['rot_center.x'],
                           model['rot_center.y'],
                           model['rot_center.z']])
    rot_ax = Quaternion(model['rot_axis.w'],
                        model['rot_axis.x'],
                        model['rot_axis.y'],
                        model['rot_axis.z'])
    rot_or = Quaternion(model['rot_orientation.w'],
                        model['rot_orientation.x'],
                        model['rot_orientation.y'],
                        model['rot_orientation.z'])

    # The rotation axis is the z axis rotated by rot_ax.
    rot_axis = rot_ax.rotate(np.array([0, 0, 1]))
    axisFrom = (rot_center + 0.1*rot_axis).tolist()
    axisTo = (rot_center - 0.1*rot_axis).tolist()

    color = [1, 0, 1]

    radius = model['rot_radius']
    if radius < 0.01:
        radius = 0.05
    angles = np.linspace(start=model['q_min[0]'], stop=model['q_max[0]'], num=100) #+1.57
    for ix in range(1, len(angles)):
        lineFrom = joint_to_point(angles[ix-1], rot_ax, rot_center, radius)
        lineTo = joint_to_point(angles[ix], rot_ax, rot_center, radius)
        #lineFrom = np.array([radius * np.cos(angles[ix]-1),
        #                     radius * np.sin(angles[ix]-1),
        #                     0.025])
        #lineTo = np.array([radius * np.cos(angles[ix]),
        #                   radius * np.sin(angles[ix]),
        #                   0.025])
        p.addUserDebugLine(lineFromXYZ=lineFrom,
                           lineToXYZ=lineTo,
                           lineColorRGB=color,
                           lineWidth=1)

    p.addUserDebugLine(lineFromXYZ=axisFrom,
                       lineToXYZ=axisTo,
                       lineColorRGB=color,
                       lineWidth=2)
    p.addUserDebugText(text='rot',
                       textPosition=axisFrom)

def draw_joints():
    if not os.path.exists(FOLDER + 'wooden_structure.json'):
        return
    with open(FOLDER + 'wooden_structure.json', 'r') as handle:
        models = json.load(handle)

    for m in models:
        if m['type'] == 'prismatic':
            draw_prismatic(m)
        elif m['type'] == 'rigid':
            draw_rigid(m)
        elif m['type'] == 'rotational':
            draw_revolute(m)
        else:
            print('cant draw type ' + m['type'] + ' yet')

# TODO: Make forces work with arbitrary revolute/prismatic joints.
def get_force_direction(world, joint_name):
    joint = world['joints'][joint_name]
    joint_position, joint_velocity, _, _ = p.getJointState(bodyUniqueId=world['model_id'],
                                                           jointIndex=joint.pybullet_id)
    lower, upper = joint.lower, joint.upper
    if joint_velocity > 0:
        direction = 1
        if not upper and math.isclose(upper, joint_position, abs_tol=0.01):
            direction = -1
    else:
        direction = -1
        if not lower is None and math.isclose(lower, joint_position, abs_tol=0.01):
            direction = 1

    return direction

def move_revolute(world, joint_name):
    joint = world['joints'][joint_name]
    link_name = joint.child_link

    direction = get_force_direction(world, joint_name)

    p.applyExternalTorque(objectUniqueId=world['model_id'],
                          linkIndex=world['links'][link_name].pybullet_id,
                          torqueObj=[0, 0, direction*0.01],
                          flags=p.WORLD_FRAME)


def move_prismatic(world, joint_name):
    joint = world['joints'][joint_name]
    link_name = joint.child_link
    direction = get_force_direction(world, joint_name)
    p.applyExternalForce(objectUniqueId=world['model_id'],
                         linkIndex=world['links'][link_name].pybullet_id,
                         forceObj=[direction*0.5, direction*0.5, 0],
                         posObj=[0, 0, 0],
                         flags=p.LINK_FRAME)


def actuate_revolute(world, gripper, joint_name):
    # TODO: need to make a function that uses the joint info to return a 3D direction
    # (unit vector) in world frame of desired motion of the joint handle
    #direction = get_force_direction(world, joint_name)
    delta_theta = -.5
    p_handle_w = p.getLinkState(world['model_id'], world['links']['spinner_handle'].pybullet_id)[0]
    p_base_w, orn_base_w = p.getLinkState(world['model_id'], world['links']['spinner'].pybullet_id)[:2]
    p_handle_base = np.subtract(p_handle_w, p_base_w)
    R = np.linalg.norm(p_handle_base[:2])
    if p_handle_base[1] > 0:
        theta = np.arccos(p_handle_base[0]/R)
    else:
        theta = -np.arccos(p_handle_base[0]/R)
    theta_new = theta + delta_theta
    p_handle_w_des = np.add([p_base_w[0], p_base_w[1], 0], [R*np.cos(theta_new), R*np.sin(theta_new), p_handle_w[2]])
    direction = np.subtract(p_handle_w_des, p_handle_w)
    unit_vector = np.divide(direction, np.linalg.norm(direction))
    magnitude = .1
    gripper.apply_force(np.multiply(magnitude, unit_vector))

def actuate_prismatic(world, gripper, joint_name):
    # TODO: need to make a function that uses the joint info to return a 3D direction
    # (unit vector) in world frame of desired motion of the joint handle
    #direction = get_force_direction(world, joint_name)
    unit_vector = [0., -1., 0.]
    magnitude = 1.0
    gripper.apply_force(np.multiply(magnitude, unit_vector))

def log_poses(world, joint_name, log_name, log):
    if joint_name == 'all':
        to_log = world['links'].keys()
    else:
        to_log = [world['joints'][joint_name].child_link, 'base_link']

    for link_name in to_log:
        if link_name == 'base_link':
            position, orientation = p.getBasePositionAndOrientation(bodyUniqueId=world['model_id'])
        else:
            position, orientation = p.getLinkState(bodyUniqueId=world['model_id'],
                                                   linkIndex=world['links'][link_name].pybullet_id)[0:2]
            if link_name == 'spinner_handle':
                orientation = p.getLinkState(world['model_id'], world['links']['spinner'].pybullet_id)[1]
        log[link_name].append(position + orientation)

    if 'spinner' in log:
        del log['spinner']
    if 'back_link' in log:
        del log['back_link']
    if 'door' in log:
        del log['door']


    with open(FOLDER + log_name, 'w') as handle:
        json.dump(log, handle)



def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-name', required=True, type=str)
    parser.add_argument('--joint-name', default='all', type=str, help='[<link_name>|all]')
    parser.add_argument('--log-name', default='', type=str, help='JSON file name')
    parser.add_argument('--duration', default=3, type=int)
    parser.add_argument('--visualize', action='store_true')
    parser.add_argument('--record', action='store_true')
    return parser.parse_args()


if __name__ == '__main__':
    args = get_arguments()
    
    recorder = Recorder(200, 200)

    # Set PyBullet configuration.
    client = p.connect(p.GUI)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -10)
    p.setRealTimeSimulation(0)
    p.resetDebugVisualizerCamera(
        cameraDistance=0.8,
        cameraYaw=210,
        cameraPitch=-52,
        cameraTargetPosition=(0., 0., 0.))
    timestep = 1. / 100.

    # Load models.
    plane_id = p.loadURDF("plane.urdf")
    world = loadUBBDF(urdf_file='models/{0}/model.urdf'.format(args.model_name),
                      ubbdf_file='models/{0}/model_relations.ubbdf'.format(args.model_name))

    # gripper = Gripper()

    # The joint motors need to be disabled before we can apply forces to them.
    maxForce = 0
    mode = p.VELOCITY_CONTROL
    for ix in range(0, p.getNumJoints(world['model_id'])):
        p.setJointMotorControl2(bodyUniqueId=world['model_id'],
                                jointIndex=ix,
                                controlMode=mode,
                                force=maxForce)

    # Simulation loop.
    log = defaultdict(list)
    if args.visualize:
        draw_joints()
        time.sleep(100)
        sys.exit(0)

    # actuate each joint sequentially with the gripper
    # gripper_orn = p.getQuaternionFromEuler([np.pi, 0., 0.])
    #for joint_name, joint in world['joints'].items():
        #if joint_name == args.joint_name or args.joint_name == 'all':

    # for joint_name in ['spinner_handle', 'prismatic_slider']:
    for tx in range(0, args.duration*10):
        for joint_name in ['revolute_door', 'prismatic_slider']:
            joint = world['joints'][joint_name]
            link_name = joint.child_link

            # grasp the joint handle
            #p_link = p.getLinkState(world['model_id'], world['links'][link_name].pybullet_id)[0]
            #if joint_name == 'spinner_handle':
            #    p_link = np.add(p_link, [0., 0., .02])
            #gripper.apply_force(finger_state='open')
            #gripper.set_tip_pose([p_link, gripper_orn])
            #gripper.apply_force(finger_state='close')

            # actuate prismatic joints
            if joint.type == 'prismatic':
                # actuate_prismatic(world, gripper, joint_name)
                move_prismatic(world, joint_name)
                for r in world['relations']:
                    r.update(world=world,
                             parent_joint=world['joints'][r.parent_joint],
                             child_joint=world['joints'][r.child_joint],
                             params=r.params)

            # actuate revolute joints
            elif joint.type == 'revolute' or joint.type == 'continuous':
                # actuate_revolute(world, gripper, joint_name)
                move_revolute(world, joint_name)
                for r in world['relations']:
                    r.update(world=world,
                             parent_joint=world['joints'][r.parent_joint],
                             child_joint=world['joints'][r.child_joint],
                             params=r.params)

        # Log poses.
        if tx % 5 == 0 and len(args.log_name) > 0:
            log_poses(world, args.joint_name, args.log_name, log)
        time.sleep(timestep)
        p.stepSimulation()

    p.disconnect()
