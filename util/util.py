import pybullet as p
import numpy as np
import pickle
import util.transformations as trans
import math
from collections import namedtuple
import os

Pose = namedtuple('Pose', 'p q')
"""
Pose represents an SE(3) pose
:param p: a vector of length 3, represeting an (x,y,z) position
:param q: a vector of length 4, representing an (x,y,z,w) quaternion
"""

Result = namedtuple('Result', 'policy_params mechanism_params motion \
                        pose_joint_world_init pose_joint_world_final config_goal \
                        image_data git_hash randomness')
"""
Result contains the performance information after the gripper tries to move a mechanism
:param policy_params: actions.policies.PolicyParams
:param mechanism_params: gen.generator_busybox.MechanismParams
:param motion: scalar, the cummulative distance the mechanism handle moved
:param pose_joint_world_init: util.Pose object, the initial pose of the mechanism handle
:param pose_joint_world_final: util.Pose object or None, the final pose of the mechanism handle if the
                    gripper tip is in contact with the mechanism at completion, else None
:param config_goal: the goal configuration which the joint was attempting to reach
:param image_data: util.util.ImageData
:param git_hash: None or str representing the git hash when the data was collected
:param randomness: float in [0,1] representing how far the policy is from the
                    correct model-based policy
"""

ImageData = namedtuple('ImageData', 'width height rgbPixels')
"""
ImageData contains a subset of the image data returned by pybullet
:param width: int, width image resolution in pixels (horizontal)
:param height: int, height image resolution in pixels (vertical)
:param rgbPixels: list of [char RED,char GREEN,char BLUE, char ALPHA] [0..width*height],
                    list of pixel colors in R,G,B,A format, in range [0..255] for each color
"""

class Recorder(object):

    def __init__(self, height, width):
        self.frames = []
        self.height = height
        self.width = width

    def capture(self):
        h, w, rgb, depth, seg = p.getCameraImage(self.width, self.height)
        self.frames.append({'rgb': rgb,
                            'depth': depth})

    def save(self, fname):
        with open(fname, 'wb') as handle:
            pickle.dump(self.frames, handle)

def write_to_file(file_name, data):
    # make directory if doesn't exist
    dir = '/'.join(file_name.split('/')[:-1])
    if not os.path.isdir(dir) and dir !='':
        os.mkdir(dir)

    # save to pickle
    with open(file_name, 'wb') as handle:
        pickle.dump(data, handle)
    print('wrote dataset to '+file_name)

def read_from_file(file_name):
    with open(file_name, 'rb') as handle:
        data = pickle.load(handle)
        print('successfully read in '+file_name)
    return data

def merge_files(in_file_names, out_file_name):
    results = []
    for file_name in in_file_names:
        result = read_from_file(file_name)
        results += result
    write_to_file(out_file_name, results)
    return results

def vis_frame(pos, quat, length=0.2, lifeTime=0.4):
    """ This function visualizes a coordinate frame for the supplied frame where the
    red,green,blue lines correpsond to the x,y,z axes.
    :param p: a vector of length 3, position of the frame (x,y,z)
    :param q: a vector of length 4, quaternion of the frame (x,y,z,w)
    """
    new_x = transformation([length, 0.0, 0.0], pos, quat)
    new_y = transformation([0.0, length, 0.0], pos, quat)
    new_z = transformation([0.0, 0.0, length], pos, quat)

    p.addUserDebugLine(pos, new_x, [1,0,0], lifeTime=lifeTime)
    p.addUserDebugLine(pos, new_y, [0,1,0], lifeTime=lifeTime)
    p.addUserDebugLine(pos, new_z, [0,0,1], lifeTime=lifeTime)

def pause():
    try:
        print('press any key to continue execution')
        while True:
            p.stepSimulation()
    except KeyboardInterrupt:
        print('trying to exit')
        return

def skew_symmetric(vec):
    """ Calculates the skew-symmetric matrix of the supplied 3 dimensional vector
    """
    i, j, k = vec
    return np.array([[0, -k, j], [k, 0, -i], [-j, i, 0]])

def adjoint_transformation(vel, translation_vec, quat, inverse=False):
    """ Converts a velocity from one frame into another
    :param vel: a vector of length 6, the velocity to be converted, [0:3] are the
            linear velocity terms and [3:6] are the angular velcoity terms
    :param translation_vec: vector of length 3, the translation (x,y,z) to the desired frame
    :param quat: vector of length 4, quaternion rotation to the desired frame
    :param inverse (optional): if True, inverts the translation_vec and quat
    """
    if inverse:
        translation_vec, quat = p.invertTransform(translation_vec, quat)

    R = p.getMatrixFromQuaternion(quat)
    R = np.reshape(R, (3,3))
    T = np.zeros((6,6))
    T[:3,:3] = R
    T[:3,3:] = skew_symmetric(translation_vec).dot(R)
    T[3:,3:] = R
    return np.dot(T, vel)

def transformation(pos, translation_vec, quat, inverse=False):
    """ Converts a position from one frame to another
    :param p: vector of length 3, position (x,y,z) in frame original frame
    :param translation_vec: vector of length 3, (x,y,z) from original frame to desired frame
    :param quat: vector of length 4, (x,y,z,w) rotation from original frame to desired frame
    :param inverse (optional): if True, inverts the translation_vec and quat
    """
    if inverse:
        translation_vec, quat = p.invertTransform(translation_vec, quat)
    R = p.getMatrixFromQuaternion(quat)
    R = np.reshape(R, (3,3))
    T = np.zeros((4,4))
    T[:3,:3] = R
    T[:3,3] = translation_vec
    T[3,3] = 1.0
    pos = np.concatenate([pos, [1]])
    new_pos = np.dot(T, pos)
    return new_pos[:3]

def quat_math(q0, q1, inv0, inv1):
    """ Performs addition and subtraction between quaternions
    :param q0: a vector of length 4, quaternion rotation (x,y,z,w)
    :param q1: a vector of length 4, quaternion rotation (x,y,z,w)
    :param inv0: if True, inverts q0
    :param inv1: if True, inverts q1

    Examples:
    to get the total rotation from going to q0 then q1: quat_math(q0,q1,False,False)
    to get the rotation from q1 to q0: quat_math(q0,q1,True,False)
    """
    if not isinstance(q0, np.ndarray):
        q0 = np.array(q0)
    if not isinstance(q1, np.ndarray):
        q1 = np.array(q1)
    q0 = to_transquat(q0)
    q0 = trans.unit_vector(q0)
    q1 = to_transquat(q1)
    q1 = trans.unit_vector(q1)
    if inv0:
        q0 = trans.quaternion_conjugate(q0)
    if inv1:
        q1 = trans.quaternion_conjugate(q1)
    res = trans.quaternion_multiply(q0,q1)
    return to_pyquat(res)

def to_transquat(pybullet_quat):
    """Convert quaternion from (x,y,z,w) returned from pybullet to
    (w,x,y,z) convention used by transformations.py"""
    return np.concatenate([[pybullet_quat[3]], pybullet_quat[:3]])

def to_pyquat(trans_quat):
    """Convert quaternion from (w,x,y,z) returned from transformations.py to
    (x,y,z,w) convention used by pybullet"""
    return np.concatenate([trans_quat[1:], [trans_quat[0]]])

def euler_from_quaternion(q):
    """Convert quaternion from (x,y,z,w) returned from pybullet to
    euler angles = (roll, pitch, yaw) convention used by transformations.py"""
    trans_quat = to_transquat(q)
    eul = trans.euler_from_quaternion(trans_quat)
    return eul

def random_quaternion(rand=None):
    trans_quat = trans.random_quaternion(rand)
    return to_pyquat(trans_quat)

### mostly taken from transformations.py ###
def pose_to_matrix(point, q):
    """Convert a pose to a transformation matrix
    """
    EPS = np.finfo(float).eps * 4.0
    q = to_transquat(q)
    n = np.dot(q, q)
    if n < EPS:
        M = np.identity(4)
        M[:3, 3] = point
        return M
    q *= math.sqrt(2.0 / n)
    q = np.outer(q, q)
    M = np.array([
        [1.0-q[2, 2]-q[3, 3],     q[1, 2]-q[3, 0],     q[1, 3]+q[2, 0], 0.0],
        [    q[1, 2]+q[3, 0], 1.0-q[1, 1]-q[3, 3],     q[2, 3]-q[1, 0], 0.0],
        [    q[1, 3]-q[2, 0],     q[2, 3]+q[1, 0], 1.0-q[1, 1]-q[2, 2], 0.0],
        [                0.0,                 0.0,                 0.0, 1.0]])
    M[:3, 3] = point
    return M

def quaternion_from_matrix(matrix, isprecise=False):
    trans_q = trans.quaternion_from_matrix(matrix)
    return to_pyquat(trans_q)

def quaternion_from_euler(roll, pitch, yaw):
    trans_q = trans.quaternion_from_euler(roll, pitch, yaw, 'rxyz')
    return to_pyquat(trans_q)

if __name__ == '__main__':
    in_names = ['data/datasets/clean_0_5000', 'data/datasets/clean_1_5000']
    out_name = 'data/datasets/clean_10000'
    merge_files(in_names, out_name)
