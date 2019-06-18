import pybullet as p
import numpy as np
from util import util
import time
from collections import namedtuple
import itertools
import sys

"""
Naming convention
-----------------
pose_ is a util.Pose()
p_ is a vector of length 3 representing a position
q_ is a vector of length 4 representing a quaternion
e_ is a vector of length 3 representing euler angles
v is a vector of length 6 with [0:3] representing the linear velocity and
                                [3:6] representing the angular velocity
lin_v is a vector of length 3 representing the linear velocity
omega is a vector of length 3 representing the angular velocity
the first following variable name represents the point/pose being described
the second following variable name indicates the frame that the point or pose is defined in

Variables
---------
world - world frame
base - gripper base frame
tip - tip of the gripper frame
com - center of mass of the entire gripper body
left - left finger tip of gripper
right - right finger tip of gripper
_err - error
_des - desired
"""

class Gripper:
    def __init__(self, bb_id, k=[2000.0,20.0], d=[0.45,0.45], add_dist=0.1, p_err_thresh=0.005):
        """
        This class defines the actions a gripper can take such as grasping a handle
        and executing PD control
        :param bb_id: int, the pybullet id of the BusyBox
        :param k: a vector of length 2 where the first entry is the linear position
                    (stiffness) gain and the second entry is the angular position gain
        :param d: a vector of length 2 where the first entry is the linear derivative
                    (damping) gain and the second entry is the angular derivative gain
        :param add_dist: scalar, the distance the PD controller is trying to control to
        :param p_err_thresh: scalar, the allowable error before the controller moves
                                to the next setpoint
        """
        self.id = p.loadSDF("../models/gripper/gripper_high_fric.sdf")[0]
        self.bb_id = bb_id
        self.left_finger_tip_id = 2
        self.right_finger_tip_id = 5
        self.left_finger_base_joint_id = 0
        self.right_finger_base_joint_id = 3
        self.finger_force = 20

        # control parameters
        self.k = k
        self.d = d
        self.add_dist = add_dist
        self.p_err_thresh = p_err_thresh

        # get mass of gripper
        mass = 0
        for link in range(p.getNumJoints(self.id)):
            mass += p.getDynamicsInfo(self.id, link)[0]
        self.mass = mass

    def get_p_tip_world(self):
        p_left_world = p.getLinkState(self.id, self.left_finger_tip_id)[0]
        p_right_world = p.getLinkState(self.id, self.right_finger_tip_id)[0]
        p_tip_world = np.mean([p_left_world, p_right_world], axis=0)
        return p_tip_world

    def get_p_tip_base(self):
        p_base_world, q_base_world = p.getBasePositionAndOrientation(self.id)
        p_tip_world = self.get_p_tip_world()
        p_tip_base = util.transformation(p_tip_world, p_base_world, q_base_world, inverse=True)
        return p_tip_base

    def get_pose_com_(self, mode):
        com_numerator = np.array([0.0, 0.0, 0.0])
        for link_index in range(p.getNumJoints(self.id)):
            link_com = p.getLinkState(self.id, link_index)[0]
            link_mass = p.getDynamicsInfo(self.id, link_index)[0]
            com_numerator = np.add(com_numerator, np.multiply(link_mass,link_com))
        p_com_world = np.divide(com_numerator, self.mass)

        p_base_world, q_base_world = p.getBasePositionAndOrientation(self.id)
        q_com_world = q_base_world

        if mode == 'world':
            return p_com_world, q_com_world
        elif mode == 'tip':
            p_tip_world = self.get_p_tip_world()
            p_com_tip = util.transformation(p_com_world, p_tip_world, q_base_world, inverse=True)
            q_com_tip = np.array([0.,0.,0.,1.])
            return p_com_tip, q_com_tip
        elif mode == 'base':
            p_com_base = util.transformation(p_com_world, p_base_world, q_base_world, inverse=True)
            q_com_base = np.array([0.0,0.0,0.0,1.0])
            return p_com_base, q_com_base

    def get_pose_error(self, pose_tip_world_des):
        p_tip_world = self.get_p_tip_world()
        q_tip_world = p.getBasePositionAndOrientation(self.id)[1]
        p_tip_world_err = np.subtract(pose_tip_world_des.p, p_tip_world)
        q_tip_world_err = util.quat_math(pose_tip_world_des.q, q_tip_world, False, True)
        e_tip_world_err = util.euler_from_quaternion(q_tip_world_err)
        return p_tip_world_err, e_tip_world_err

    def get_v_com_world_error(self, v_tip_world_des):
        p_com_tip, q_com_tip = self.get_pose_com_('tip')
        v_com_world_des = util.adjoint_transformation(v_tip_world_des, p_com_tip, q_com_tip, inverse=True)

        v_base_world = np.concatenate(p.getBaseVelocity(self.id))
        p_com_base, q_com_base = self.get_pose_com_('base')
        v_com_world = util.adjoint_transformation(v_base_world, p_com_base, q_com_base, inverse=True)

        v_com_world_err = np.subtract(v_com_world_des, v_com_world)
        return v_com_world_err[:3], v_com_world_err[3:]

    def at_des_pose(self, pose_tip_world_des):
        p_tip_world_err, _ = self.get_pose_error(pose_tip_world_des)
        return np.linalg.norm(p_tip_world_err) < self.p_err_thresh

    def in_contact(self, mech):
        points = p.getContactPoints(self.id, self.bb_id, linkIndexB=mech.handle_id)
        if len(points)>0:
            return True
        return False

    def set_pose_tip_world(self, pose_tip_world_des, reset=False):
        p_base_tip = np.multiply(-1, self.get_p_tip_base())
        p_base_world_des = util.transformation(p_base_tip, pose_tip_world_des.p, pose_tip_world_des.q)
        p.resetBasePositionAndOrientation(self.id, p_base_world_des, pose_tip_world_des.q)
        p.stepSimulation()

    def grasp_handle(self, pose_tip_world_des, debug=False):
        # move to default start pose
        p_tip_world_init = [0.0, 0.0, 0.2]
        q_tip_world_init = [0.50019904,  0.50019904, -0.49980088, 0.49980088]
        pose_tip_world_init = util.Pose(p_tip_world_init, q_tip_world_init)
        for t in range(10):
            self.set_pose_tip_world(pose_tip_world_init, reset=True)

        # open fingers
        for t in range(10):
            self.control_fingers('open', debug=debug)

        # move to desired pose
        for t in range(10):
            self.set_pose_tip_world(pose_tip_world_des, reset=True)

        # close fingers
        for t in range(10):
            self.control_fingers('close', debug=debug)

    def control_fingers(self, finger_state, debug=False):
        if finger_state == 'open':
            finger_angle = 0.2
        elif finger_state == 'close':
            finger_angle = 0.0
        p.setJointMotorControl2(self.id,self.left_finger_base_joint_id,p.POSITION_CONTROL,targetPosition=-finger_angle,force=self.finger_force)
        p.setJointMotorControl2(self.id,self.right_finger_base_joint_id,p.POSITION_CONTROL,targetPosition=finger_angle,force=self.finger_force)
        p.setJointMotorControl2(self.id,2,p.POSITION_CONTROL,targetPosition=0,force=self.finger_force)
        p.setJointMotorControl2(self.id,5,p.POSITION_CONTROL,targetPosition=0,force=self.finger_force)
        p.stepSimulation()

    def move_PD(self, pose_tip_world_des, debug=False, timeout=100):
        # move setpoint further away in a straight line between curr pose and goal pose
        dir = np.subtract(pose_tip_world_des.p, self.get_p_tip_world())
        mag = np.linalg.norm([dir])
        unit_dir = np.divide(dir,mag)
        p_tip_world_des_far = np.add(pose_tip_world_des.p,np.multiply(self.add_dist,unit_dir))
        pose_tip_world_des_far = util.Pose(p_tip_world_des_far, pose_tip_world_des.q)
        finished = False
        for i in itertools.count():
            # keep fingers closed (doesn't seem to make a difference but should
            # probably continually close fingers)
            self.control_fingers('close', debug=debug)
            if debug:
                p.addUserDebugLine(pose_tip_world_des_far.p, np.add(pose_tip_world_des_far.p,[0,0,10]), lifeTime=.5)
                p.addUserDebugLine(pose_tip_world_des.p, np.add(pose_tip_world_des.p,[0,0,10]), [1,0,0], lifeTime=.5)
                p_tip_world = self.get_p_tip_world()
                p.addUserDebugLine(p_tip_world, np.add(p_tip_world,[0,0,10]), [0,1,0], lifeTime=.5)
                err = self.get_pose_error(pose_tip_world_des)
                if debug:
                    sys.stdout.write("\r%.3f %.3f" % (np.linalg.norm(err[0]), np.linalg.norm(err[1])))
                util.vis_frame(*pose_tip_world_des)
            if self.at_des_pose(pose_tip_world_des):
                finished = True
                break
            if i>timeout:
                if debug:
                    print('timeout limit reached. moving the next joint')
                break
            p_tip_world_err, e_tip_world_err = self.get_pose_error(pose_tip_world_des_far)
            v_tip_world_des = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            lin_v_com_world_err, omega_com_world_err = self.get_v_com_world_error(v_tip_world_des)

            f = np.multiply(self.k[0], p_tip_world_err) + np.multiply(self.d[0], lin_v_com_world_err)
            tau = np.multiply(self.k[1], e_tip_world_err) + np.multiply(self.d[1], omega_com_world_err)

            p_com_world, q_com_world = self.get_pose_com_('world')
            p.applyExternalForce(self.id, -1, f, p_com_world, p.WORLD_FRAME)
            # there is a bug in pyBullet. the link frame and world frame are inverted
            # this should be executed in the WORLD_FRAME
            p.applyExternalTorque(self.id, -1, tau, p.LINK_FRAME)
            p.stepSimulation()
        return finished

    def execute_trajectory(self, grasp_pose, traj, debug=False, callback=None, bb=None, mech=None):
        self.grasp_handle(grasp_pose, debug)
        start_time = time.time()
        motion = 0.0
        for (i, pose_tip_world_des) in enumerate(traj):
            if mech:
                start_mech_pose = p.getLinkState(self.bb_id, mech.handle_id)[0]
            finished = self.move_PD(pose_tip_world_des, debug)
            if mech:
                final_mech_pose = p.getLinkState(self.id, mech.handle_id)[0]
                motion += np.linalg.norm(np.subtract(final_mech_pose,start_mech_pose))
            if not finished:
                break
            if not callback is None:
                callback(bb)
        duration = time.time() - start_time
        return i/len(traj), duration, motion
