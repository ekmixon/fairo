"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
# python -m Pyro4.naming -n <MYIP>
import Pyro4
from stretch_body.robot import Robot
from colorama import Fore, Back, Style
import stretch_body.hello_utils as hu
hu.print_stretch_re_use()
import numpy as np
import logging
import os
import json
import time
import pyrealsense2 as rs
import cv2
from math import *
from slam_pkg.slam import Slam
import copy
from droidlet.lowlevel.hello_robot.remote.utils import transform_global_to_base, goto
from slam_pkg.utils import depth_util as du


# Configure depth and color streams
CAMERA_HEIGHT = 1.5
CH = 480
CW = 640
FREQ = 30

Pyro4.config.SERIALIZER = "pickle"
Pyro4.config.SERIALIZERS_ACCEPTED.add("pickle")
Pyro4.config.ITER_STREAMING = True

def val_in_range(val_name, val,vmin, vmax):
    p=val <=vmax and val>=vmin
    if p:
        print(Fore.GREEN +'[Pass] ' + val_name + ' with ' + str(val))
    else:
        print(Fore.RED +'[Fail] ' + val_name + ' with ' +str(val)+ ' out of range ' +str(vmin) + ' to ' + str(vmax))

# #####################################################

@Pyro4.expose
class RemoteHelloRobot(object):
    """Hello Robot interface"""

    def __init__(self):
        self._robot = Robot()
        self._robot.startup()
        if not self._robot.is_calibrated():
            self._robot.home()
        self._robot.stow()
        self._done = True
        # Read battery maintenance guide https://docs.hello-robot.com/battery_maintenance_guide/
        self._check_battery()
        self._connect_to_realsense()
        # Slam stuff
        #uv_one_in_cam
        intrinsic_mat = np.asarray(self.get_intrinsics())
        intrinsic_mat_inv = np.linalg.inv(intrinsic_mat)
        img_resolution = self.get_img_resolution()
        img_pixs = np.mgrid[0 : img_resolution[1] : 1, 0 : img_resolution[0] : 1] # Camera on the hello is oriented vertically
        img_pixs = img_pixs.reshape(2, -1)
        img_pixs[[0, 1], :] = img_pixs[[1, 0], :]
        uv_one = np.concatenate((img_pixs, np.ones((1, img_pixs.shape[1]))))
        self.uv_one_in_cam = np.dot(intrinsic_mat_inv, uv_one)
        self._slam = Slam(self, robot_name='hello')
        self._slam_step_size = 25  # step size in cm
    
    def _load_urdf(self):
        import os
        urdf_path = os.path.join(os.getenv("HELLO_FLEET_PATH"), os.getenv("HELLO_FLEET_ID"), "exported_urdf", "stretch.urdf")

        from pytransform3d.urdf import UrdfTransformManager
        import pytransform3d.transformations as pt
        import pytransform3d.visualizer as pv
        import numpy as np

        self.tm = UrdfTransformManager()
        with open(urdf_path, "r") as f:
            urdf = f.read()
            self.tm.load_urdf(urdf)
        
    def get_camera_transform(self):
        s = self._robot.get_status()
        head_pan = s['head']['head_pan']['pos']
        head_tilt = s['head']['head_tilt']['pos']

        # Get Camera transform
        self.tm.set_joint("joint_head_pan", head_pan)
        self.tm.set_joint("joint_head_pan", head_pan)
        camera_transform = self.tm.get_transform('camera_link', 'base_link')

        return camera_transform

    def get_rgb_depth(self):
        tm = time.time()
        frames = None
        while not frames:
            frames = self.realsense.wait_for_frames()
            aligned_frames = self.align.process(frames)

            # Get aligned frames
            aligned_depth_frame = aligned_frames.get_depth_frame() # aligned_depth_frame is a 640x480 depth image
            color_frame = aligned_frames.get_color_frame()

            # Validate that both frames are valid
            if not aligned_depth_frame or not color_frame:
                continue

            depth_image = np.asanyarray(aligned_depth_frame.get_data())/1000.0 # convert to meters
            color_image = np.asanyarray(color_frame.get_data())

            # rotate 
            depth_image = np.rot90(depth_image, k=1, axes=(1,0))
            color_image = np.rot90(color_image, k=1, axes=(1,0))

        return color_image, depth_image


    def get_pcd_data(self):
        """Gets all the data to calculate the point cloud for a given rgb, depth frame."""
        rgb, depth = self.get_rgb_depth()
        depth *= 1000  # convert to mm
        # cap anything more than np.power(2,16)~ 65 meter
        depth[depth > np.power(2, 16) - 1] = np.power(2, 16) - 1
        depth = depth.astype(np.uint16)
        T = self.get_camera_transform()
        rot = T[:3, :3]
        trans = T[:3, 3]
        base2cam_trans = np.array(trans).reshape(-1, 1)
        base2cam_rot = np.array(rot)
        return rgb.tolist(), depth.tolist(), base2cam_rot.tolist(), base2cam_trans.tolist()

    def get_current_pcd(self):
        rgb, depth, rot, trans = self.get_pcd_data()
        rgb = np.asarray(rgb).astype(np.uint8)
        rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)
        depth = np.asarray(depth)
        rot = np.asarray(rot)
        trans = np.asarray(trans)
        depth = depth.astype(np.float32)
        d = copy.deepcopy(depth)
        depth /= 1000.0
        depth = depth.reshape(-1)
        pts_in_cam = np.multiply(self.uv_one_in_cam, depth)
        pts_in_cam = np.concatenate((pts_in_cam, np.ones((1, pts_in_cam.shape[1]))), axis=0)
        pts = pts_in_cam[:3, :].T
        pts = np.dot(pts, rot.T)
        pts = pts + trans.reshape(-1)
        pts = du.transform_pose(pts, self.get_base_state())
        return pts

    def _connect_to_realsense(self):
        cfg = rs.config()
        pipeline = rs.pipeline()
        cfg.enable_stream(rs.stream.color, CW, CH, rs.format.bgr8, 30)
        cfg.enable_stream(rs.stream.depth, CW, CH, rs.format.z16, 30)
        pipeline.start(cfg)
        self.realsense = pipeline

        profile = pipeline.get_active_profile()
        depth_profile = rs.video_stream_profile(profile.get_stream(rs.stream.depth))
        i = depth_profile.get_intrinsics()
        # camera on the robot is oriented vertically, so x and y axes are swapped
        self.intrinsic_mat = np.array([[i.fy, 0,    i.ppy],
                                       [0,    i.fx, i.ppx],
                                       [0,    0,    1]])
        align_to = rs.stream.color
        self.align = rs.align(align_to)
        print("connected to realsense")

    def _check_battery(self):
        p = self._robot.pimu
        p.pull_status()
        val_in_range('Voltage',p.status['voltage'], vmin=p.config['low_voltage_alert'], vmax=14.0)
        val_in_range('Current',p.status['current'], vmin=0.1, vmax=p.config['high_current_alert'])
        val_in_range('CPU Temp',p.status['cpu_temp'], vmin=15, vmax=80)
        print(Style.RESET_ALL)
    
    def explore(self):
        if self._done:
            self._done = False
            if not self._slam.whole_area_explored:
                self._slam.set_goal(
                    (19, 19, 0)
                )  # set  far away goal for exploration, default map size [-20,20]
                self._slam.take_step(self._slam_step_size)
            self._done = True
            return True

    def get_intrinsics(self):
        return self.intrinsic_mat.tolist()

    def get_img_resolution(self):
        return (CH, CW)

    def get_status(self):
        return self._robot.get_status()

    def get_base_state(self):
        s = self._robot.get_status()
        return (s['base']['x'], s['base']['y'], (s['base']['theta'] % radians(360)))

    def get_pan(self):
        s = self._robot.get_status()
        return s['head']['head_pan']['pos']

    def get_tilt(self):
        s = self._robot.get_status()
        return s['head']['head_tilt']['pos']

    def set_pan(self, pan):
        self._robot.head.move_to('head_pan', pan)

    def set_tilt(self, tilt):
        self._robot.head.move_to('head_tilt', tilt)
    
    def reset_camera(self):
        self.set_pan(0)
        self.set_tilt(0)

    def set_pan_tilt(self, pan, tilt):
        """Sets both the pan and tilt joint angles of the robot camera  to the
        specified values.

        :param pan: value to be set for pan joint in radian
        :param tilt: value to be set for the tilt joint in radian

        :type pan: float
        :type tilt: float
        :type wait: bool
        """
        self._robot.head.move_to('head_pan', pan)
        self._robot.head.move_to('head_tilt', tilt)

    def test_connection(self):
        print("Connected!!")  # should print on server terminal
        return "Connected!"  # should print on client terminal

    def home(self):
        self._robot.home()

    def stow(self):
        self._robot.stow()

    def push_command(self):
        self._robot.push_command()

    def translate_by(self, x_m):
        self._robot.base.translate_by(x_m)
        self._robot.push_command()

    def rotate_by(self, x_r):
        self._robot.base.rotate_by(x_r)
        self._robot.push_command()

    def go_to_absolute(
        self,
        xyt_position,
        use_map=False,
        close_loop=True,
        smooth=False,
        use_dslam=False,
    ):
        """Moves the robot base to given goal state in the world frame.

        :param xyt_position: The goal state of the form (x,y,yaw)
                             in the world (map) frame.
        :param use_map: When set to "True", ensures that controller is
                        using only free space on the map to move the robot.
        :param close_loop: When set to "True", ensures that controller
                           is operating in open loop by taking
                           account of odometry.
        :param smooth: When set to "True", ensures that the motion
                       leading to the goal is a smooth one.
        :param use_dslam: When set to "True", the robot uses slam for
                          the navigation.

        :type xyt_position: list or np.ndarray
        :type use_map: bool
        :type close_loop: bool
        :type smooth: bool
        """
        assert(use_map == False)
        assert(close_loop == True)
        assert(smooth == False)
        assert(use_dslam == False)
        if self._done:
            self._done = False
            if use_dslam:
                self._slam.set_absolute_goal_in_robot_frame(xyt_position)
            else:
                global_xyt = xyt_position
                base_state = self.get_base_state()
                base_xyt = transform_global_to_base(global_xyt, base_state)
                goto(self._robot, list(base_xyt), dryrun=False)
            self._done = True

    def go_to_relative(
        self,
        xyt_position,
        use_map=False,
        close_loop=True,
        smooth=False,
        use_dslam=False,
    ):
        """Moves the robot base to the given goal state relative to its current
        pose.

        :param xyt_position: The  relative goal state of the form (x,y,yaw)
        :param use_map: When set to "True", ensures that controller is
                        using only free space on the map to move the robot.
        :param close_loop: When set to "True", ensures that controller is
                           operating in open loop by taking
                           account of odometry.
        :param smooth: When set to "True", ensures that the
                       motion leading to the goal is a smooth one.
        :param use_dslam: When set to "True", the robot uses slam for
                          the navigation.

        :type xyt_position: list or np.ndarray
        :type use_map: bool
        :type close_loop: bool
        :type smooth: bool
        """
        assert(use_map == False)
        assert(close_loop == True)
        assert(smooth == False)
        assert(use_dslam == False)
        if self._done:
            self._done = False
            if use_dslam:
                self._slam.set_relative_goal_in_robot_frame(xyt_position)
            else:
                goto(self._robot, list(xyt_position), dryrun=False)
            self._done = True


    def get_rgb_depth(self):
        tm = time.time()
        frames = None
        while not frames:
            frames = self.realsense.wait_for_frames()
            aligned_frames = self.align.process(frames)

            # Get aligned frames
            aligned_depth_frame = aligned_frames.get_depth_frame() # aligned_depth_frame is a 640x480 depth image
            color_frame = aligned_frames.get_color_frame()

            # Validate that both frames are valid
            if not aligned_depth_frame or not color_frame:
                continue

            depth_image = np.asanyarray(aligned_depth_frame.get_data())/1000 # convert to meters
            color_image = np.asanyarray(color_frame.get_data())

            # rotate 
            depth_image = np.rot90(depth_image, k=1, axes=(1,0))
            color_image = np.rot90(color_image, k=1, axes=(1,0))

        return color_image, depth_image


    def get_pcd_data(self):
        """Gets all the data to calculate the point cloud for a given rgb, depth frame."""
        rgb, depth = self.get_rgb_depth()
        depth *= 1000  # convert to mm
        # cap anything more than np.power(2,16)~ 65 meter
        depth[depth > np.power(2, 16) - 1] = np.power(2, 16) - 1
        depth = depth.astype(np.uint16)
        #FIXME THIS IS BROKEN!! (deal with pitch)
        trans = [0, 0, CAMERA_HEIGHT]
        rot = np.array([[0., 0., 1.], [-1., 0., 0.], [0., -1.,0.]])
        T = np.eye(4)
        T[:3,:3] = rot
        T[:3,3] = trans
        base2cam_trans = np.array(trans).reshape(-1, 1)
        base2cam_rot = np.array(rot)
        return rgb.tolist(), depth.tolist(), base2cam_rot.tolist(), base2cam_trans.tolist()

    def get_current_pcd(self):
        rgb, depth, rot, trans = self.get_pcd_data()
        rgb = np.asarray(rgb).astype(np.uint8)
        rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)
        depth = np.asarray(depth)
        rot = np.asarray(rot)
        trans = np.asarray(trans)
        depth = depth.astype(np.float32)
        d = copy.deepcopy(depth)
        depth /= 1000.0
        depth = depth.reshape(-1)
        pts_in_cam = np.multiply(self.uv_one_in_cam, depth)
        pts_in_cam = np.concatenate((pts_in_cam, np.ones((1, pts_in_cam.shape[1]))), axis=0)
        pts = pts_in_cam[:3, :].T
        pts = np.dot(pts, rot.T)
        pts = pts + trans.reshape(-1)
        pts = du.transform_pose(pts, self.get_base_state())
        return pts

    def get_map(self):
        """returns the location of obstacles created by slam only for the obstacles,"""
        # get the index correspnding to obstacles
        indices = np.where(self._slam.map_builder.map[:, :, 1] >= 1.0)
        # convert them into robot frame
        real_world_locations = [
            self._slam.map2real([indice[0], indice[1]]).tolist()
            for indice in zip(indices[0], indices[1])
        ]
        return real_world_locations

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pass in server device IP")
    parser.add_argument(
        "--ip",
        help="Server device (robot) IP. Default is 192.168.0.0",
        type=str,
        default="172.20.7.104",
    )

    args = parser.parse_args()

    np.random.seed(123)

    with Pyro4.Daemon(args.ip) as daemon:
        robot = RemoteHelloRobot()
        robot_uri = daemon.register(robot)
        with Pyro4.locateNS() as ns:
            ns.register("remotehellorobot", robot_uri)

        print("Server is started...")
        daemon.requestLoop()
