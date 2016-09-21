# Author: Sudeep Pillai <spillai@csail.mit.edu>
# License: MIT

import os
import sys
import time
import numpy as np
from itertools import izip

from pybot.geometry.rigid_transform import RigidTransform, Pose, Quaternion
from pybot.vision.image_utils import to_color, to_gray
from pybot.vision.imshow_utils import imshow_cv
from pybot.utils.pose_utils import PoseAccumulator
from pybot.utils.misc import Accumulator, SkippedCounter, CounterWithPeriodicCallback
from pybot.externals.lcm import draw_utils

# Import GTSAM / ISAM
_BACKEND = 'gtsam'
if 'PYBOT_BACKEND' in os.environ:
    _backend = os.environ['PYBOT_BACKEND']
    assert _backend in {'gtsam', 'isam'}
    _BACKEND = _backend

if _BACKEND == 'gtsam':
    sys.stderr.write('Using GTSAM backend.\n')
    from pybot.mapping.gtsam import BaseSLAM as _BaseSLAM
    from pybot.mapping.gtsam import VisualSLAM as _VisualSLAM
elif _BACKEND == 'isam':
    sys.stderr.write('Using iSAM backend.\n')
    raise NotImplementedError('ISAM not yet implemented')
else:
    raise Exception('Unknown backend: ' + str(_BACKEND))

class BaseSLAM(_BaseSLAM):
    def __init__(self): 
        _BaseSLAM.__init__(self)
        self.q_poses_ = Accumulator(maxlen=2)

    def on_odom_absolute(self, t, p): 
        """
        Accumulate poses (input: absolute odometry) and add relative odometry to 
        factor graph with appropriate timestamp

           1. On the first odometry data, pose graph is initialized
           2. On the second and subsequent odometry measurements, 
              relative pose measurement is added 
        
        """
        # Initialize keyframes if not previously done
        # Add odometry measurements incrementally
        self.q_poses_.accumulate(p) 

        # 1. SLAM: Initialize
        if not self.is_initialized: 
            self.initialize(self.q_poses_.latest.matrix)
            return self.latest
        assert(self.q_poses_.length >= 2)

        # 2. SLAM: Add relative pose measurements (odometry)
        p_odom = (self.q_poses_.items[-2].inverse()).oplus(self.q_poses_.items[-1])
        self.add_odom_incremental(p_odom.matrix)

        if self.latest >= 2 and self.latest % 10 == 0: 
            self.update()

        return self.latest

    def on_odom_relative(self, t, p): 
        """
        Accumulate componded pose (input: relative odometry) and add relative odometry to 
        factor graph with appropriate timestamp
        """
        # 1. SLAM: Initialize
        if not self.is_initialized: 
            self.initialize(RigidTransform.identity().matrix)
        
        # 2. SLAM: Add relative pose measurements (odometry)
        self.add_odom_incremental(p.matrix)

        if self.latest >= 2 and self.latest % 10 == 0: 
            self.update()

        # 3. Visualize
        # self.vis_optimized()

        return self.latest

    # def on_point_landmarks_smart(self, t, ids, pts, keep_tracked=True): 
    #     assert(self.smart_)
    #     self.add_point_landmarks_incremental_smart(ids, pts, keep_tracked=keep_tracked)
    #     if self.q_poses_.length >= 2: 
    #         self.update()
    #         # self.update_marginals()
    #         ids, pts3 = self.smart_update()

    #         # Publish pose
    #         draw_utils.publish_pose_list('gtsam-pose', [Pose.from_rigid_transform(t, self.q_poses_.latest)], 
    #                                      frame_id='camera', reset=False)
    #         # Publish cloud in latest pose reference frame
    #         if len(pts3): 
    #             pts3 = RigidTransform.from_matrix(self.pose(self.latest)).inverse() * pts3
    #         draw_utils.publish_cloud('gtsam-pc', [pts3], c='b', frame_id='gtsam-pose', element_id=[t], reset=False)

    #     # self.vis_optimized()

    #     return self.latest

    def on_pose_landmarks(self, t, ids, poses): 
        deltas = [p.matrix for p in poses]
        self.add_pose_landmarks_incremental(ids, deltas)

        # if self.q_poses_.length >= 2 and self.q_poses_.length % 10 == 0: 
        #     self._update()
        #     self._update_marginals()
            
        #     if self.smart_: 
        #         ids, pts3 = self.smart_update()

        #     # # Publish pose
        #     # draw_utils.publish_pose_list('gtsam-pose', [Pose.from_rigid_transform(t, self.q_poses_.latest)], 
        #     #                              frame_id='camera', reset=False)

        #     # # Publish cloud in latest pose reference frame
        #     # if len(pts3): 
        #     #     pts3 = RigidTransform.from_matrix(self.pose(self.latest)).inverse() * pts3
        #     # draw_utils.publish_cloud('gtsam-pc', [pts3], c='b', frame_id='gtsam-pose', element_id=[t], reset=False)

        # # self.vis_optimized()

        return self.latest

    def update(self): 
        self._update()
        self._update_marginals()


class BaseSLAMWithViz(BaseSLAM): 
    def __init__(self, name='SLAM-', frame_id='camera'): 
        BaseSLAM.__init__(self)

        self.name_ = name
        self.frame_id_ = frame_id

    def on_odom_absolute(self, t, p): 
        BaseSLAM.on_odom_absolute(self, t, p_bm)
        # draw_utils.publish_pose_list(self.name_ + 'measured_factor_odom', 
        #                              [Pose.from_rigid_transform(self.q_poses_.index, self.q_poses_.latest)], 
        #                              frame_id=self.frame_id_, reset=False)

    def on_odom_relative(self, t, p): 
        BaseSLAM.on_odom_relative(self, t, p_bm)
        # draw_utils.publish_pose_list(self.name_ + 'measured_factor_odom', 
        #                              [Pose.from_rigid_transform(self.q_poses_.index, self.q_poses_.latest)], 
        #                              frame_id=self.frame_id_, reset=False)

    def on_pose_landmarks(self, t, ids, poses): 
        BaseSLAM.on_pose_landmarks(self, t, ids, poses)
        draw_utils.publish_pose_list(self.name_ + 'landmarks', [Pose.from_rigid_transform(pid, p) 
                                                    for (pid, p) in izip(ids, poses)], 
                                     frame_id=self.frame_id_, reset=False)

        


# class RobotSLAMMixin(object): 
#     def __init__(self, landmark_type='point', smart=False, update_on_odom=False, 
#                  visualize_factors=False, visualize_nodes=False, visualize_marginals=False): 
#         if not isinstance(self, (GTSAM_BaseSLAM, GTSAM_VisualSLAM)): 
#             raise RuntimeError('Cannot mixin without mixing with one of the SLAM classes')
#         if not ((isinstance(self, GTSAM_BaseSLAM) and landmark_type == 'pose') or 
#                 (isinstance(self, GTSAM_VisualSLAM) and landmark_type == 'point')): 
#             raise ValueError('Wrong expected landmark type for {}, provided {}'
#                              .format(type(self), landmark_type))

#         self.landmark_type_ = landmark_type
#         self.update_on_odom_ = update_on_odom

#         # Visualizations
#         self.visualize_factors_ = visualize_factors
#         self.visualize_nodes_ = visualize_nodes
#         self.visualize_marginals_ = visualize_marginals

#         self.landmark_text_lut_ = {}
#         self.smart_ = smart
#         self.slam_mixin_timing_st_ = time.time()

#     @property
#     def is_smart(self): 
#         return self.smart_

#     def set_landmark_texts(self, landmark_lut): 
#         " {landmark id -> landmark str, ... }"
#         self.landmark_text_lut_ = landmark_lut


#     def finish(self): 
#         for j in range(10): 
#             self.update()
#         self.update_marginals()
#         if self.smart_: 
#             ids, pts3 = self.smart_update()
#         self.vis_optimized()
#         print('{} :: Finished/Solved in {:4.2f} s'.format(self.__class__.__name__, time.time() - self.slam_mixin_timing_st_))

#     #################
#     # Visualization #
#     #################

#     def vis_measurements(self, frame_id='camera'): 
#         poses = self.q_poses_
#         assert(isinstance(poses, Accumulator))

#         # Draw robot poses
#         # draw_utils.publish_pose_t('POSE', poses.latest, frame_id=frame_id)
#         # draw_utils.publish_pose_list('CAMERA_POSES', [Pose.from_rigid_transform(poses.index, poses.latest)], 
#         #                              frame_id=frame_id, reset=False)

#         # Draw odometry link
#         if poses.length >= 2:
#             p_odom = (poses.items[-2].inverse()).oplus(poses.items[-1])
#             factor_st = (poses.items[-2].tvec).reshape(-1,3)
#             factor_end = (poses.items[-1].tvec).reshape(-1,3)
#             draw_utils.publish_line_segments('measured_factor_odom', factor_st, factor_end, c='r', 
#                                              frame_id=frame_id, reset=False)

#     def vis_optimized(self, frame_id='camera'): 
#         """
#         Update SLAM visualizations with optimized factors
#         """
#         if not self.visualize_nodes_ and \
#            not self.visualize_factors_ and \
#            not self.visualize_marginals_: 
#             return 

#         # if not draw_utils.has_sensor_frame('optcamera'): 
#         #     draw_utils.publish_sensor_frame()

#         # =========================================================
#         # POSES/MARGINALS

#         # Poses 
#         covars = []
#         updated_poses = {pid : Pose.from_rigid_transform(
#             pid, RigidTransform.from_matrix(p)) 
#                          for (pid,p) in self.poses.iteritems()}

#         # Marginals
#         if self.visualize_marginals_: 
#             poses_marginals = self.poses_marginals
#             triu_inds = np.triu_indices(3)
#             if self.marginals_available: 
#                 for pid in updated_poses.keys(): 
#                     covars.append(
#                         poses_marginals.get(pid, np.eye(6, dtype=np.float32) * 100)[triu_inds]
#                     )

#         # Draw cameras (with poses and marginals)
#         draw_utils.publish_cameras('optimized_node_poses', updated_poses.values(), 
#                                    covars=covars, frame_id=frame_id, draw_edges=False, reset=True)

#         # Draw odometry edges (between robot poses)
#         if self.visualize_factors_: 
#             robot_edges = self.robot_edges
#             if len(robot_edges): 
#                 factor_st = np.vstack([(updated_poses[xid].tvec).reshape(-1,3) for (xid, _) in robot_edges])
#                 factor_end = np.vstack([(updated_poses[xid].tvec).reshape(-1,3) for (_, xid) in robot_edges])

#                 draw_utils.publish_line_segments('optimized_factor_odom', factor_st, factor_end, c='b', 
#                                                  frame_id=frame_id, reset=True) 


#         # =========================================================
#         # TARGETS/LANDMARKS

#         if self.landmark_type_ == 'pose': 
#             # Draw targets (constantly updated, so draw with reset)
#             updated_targets = {pid : Pose.from_rigid_transform(pid, RigidTransform.from_matrix(p)) 
#                                for (pid, p) in self.target_poses.iteritems()}
#             if len(updated_targets): 
#                 texts = [self.landmark_text_lut_.get(k, str(k)) for k in updated_targets.keys()]
#                 draw_utils.publish_pose_list('optimized_node_landmark', updated_targets.values(), 
#                                              texts=texts, reset=True)

#                 # edges = np.vstack([draw_utils.draw_tag_edges(p) for p in updated_targets.itervalues()])
#                 # draw_utils.publish_line_segments('optimized_node_landmark', edges[:,:3], edges[:,3:6], c='r', 
#                 #                                  frame_id=frame_id, reset=True)
#                 # draw_utils.publish_tags('optimized_node_landmark', updated_targets.values(), 
#                 #                         texts=map(str, updated_targets.keys()), draw_nodes=True, draw_edges=True, 
#                 #                         frame_id=frame_id, reset=True)

#             # Draw edges (between landmarks and poses)
#             if self.visualize_factors_: 
#                 landmark_edges = self.landmark_edges
#                 if len(landmark_edges): 
#                     factor_st = np.vstack([(updated_poses[xid].tvec).reshape(-1,3) for (xid, _) in landmark_edges])
#                     factor_end = np.vstack([(updated_targets[lid].tvec).reshape(-1,3) for (_, lid) in landmark_edges])

#                     draw_utils.publish_line_segments('optimized_factor_landmark', factor_st, factor_end, c='b', 
#                                                      frame_id=frame_id, reset=True) 

#         elif self.landmark_type_ == 'point': 

#             # Draw targets (constantly updated, so draw with reset)
#             updated_targets = {pid : pt3
#                                for (pid, pt3) in self.target_landmarks.iteritems()}
#             if len(updated_targets): 
#                 points3d = np.vstack(updated_targets.values())
#                 draw_utils.publish_cloud('optimized_node_landmark', points3d, c='r', 
#                                          frame_id=frame_id, reset=True)

#             # Landmark points
#             if self.visualize_nodes_: 
#                 covars = []
#                 poses = [Pose(k, tvec=v) for k, v in updated_targets.iteritems()]
#                 texts = [self.landmark_text_lut_.get(k, '') for k in updated_targets.keys()] \
#                         if len(self.landmark_text_lut_) else []

#                 # Marginals
#                 if self.visualize_marginals_: 
#                     target_landmarks_marginals = self.target_landmarks_marginals
#                     triu_inds = np.triu_indices(3)
#                     if self.marginals_available: 
#                         for pid in updated_targets.keys(): 
#                             covars.append(
#                                 target_landmarks_marginals.get(pid, np.ones(shape=(6,6)) * 10)[triu_inds]
#                             )

#                 # Draw landmark points
#                 draw_utils.publish_pose_list('optimized_node_landmark_poses', poses, texts=texts, 
#                                              covars=covars, frame_id=frame_id, reset=True)

#             # Draw edges (between landmarks and poses)
#             if self.visualize_factors_: 
#                 landmark_edges = self.landmark_edges
#                 if len(landmark_edges): 
#                     factor_st = np.vstack([(updated_poses[xid].tvec).reshape(-1,3) for (xid, _) in landmark_edges])
#                     factor_end = np.vstack([(updated_targets[lid]).reshape(-1,3) for (_, lid) in landmark_edges])

#                     draw_utils.publish_line_segments('optimized_factor_landmark', factor_st, factor_end, c='b', 
#                                                      frame_id=frame_id, reset=True) 

#         else: 
#             raise ValueError('Unknown landmark_type {:}'.format(self.landmark_type_))

#         # Maintain updated ids
#         return set(updated_poses.keys())


#     def vis_landmarks(self, pose_id, p_latest, p_landmarks, frame_id='camera', landmark_name='tag'): 
#         """
#         Visualize tags with respect to latest camera frame
#         """
#         if not len(p_landmarks): 
#             return

#         # Accumulate tag detections into global reference frame
#         p_Wc = p_latest
#         p_Wt = [Pose.from_rigid_transform(pose_id * 20 + p.id, p_Wc.oplus(p)) for p in p_landmarks]

#         # Plot RAW tag factors
#         factor_st = np.tile(p_latest.tvec, [len(p_Wt),1])
#         factor_end = np.vstack(map(lambda p: p.tvec, p_Wt))

#         factor_ct_end = np.vstack([p.tvec for p in p_landmarks])
#         factor_ct_st = np.zeros_like(factor_ct_end)

#         draw_utils.publish_line_segments('measured_factor_{:}'.format(landmark_name), factor_st, factor_end, c='b', 
#                                          frame_id=frame_id, reset=self.reset_required())
#         edges = np.vstack([draw_utils.draw_tag_edges(p) for p in p_Wt])
#         draw_utils.publish_line_segments('measured_node_{:}'.format(landmark_name), edges[:,:3], edges[:,3:6], c='b', 
#                                          frame_id=frame_id, reset=self.reset_required())

#         # # Optionally plot as Tags
#         # draw_utils.publish_pose_list('RAW_tags', p_Wt, texts=[], object_type='TAG', 
#         #                              frame_id=frame_id, reset=self.reset_required())

        
#         # # Plot OPTIMIZED tag factors
#         # if pose_id in self.updated_ids_: 
#         #     draw_utils.publish_line_segments('OPT_factors_{:}'.format(landmark_name), factor_ct_st, factor_ct_end, c='r', 
#         #                                  frame_id='optimized_poses', element_id=pose_id, reset=self.reset_required())

#         #     edges = np.vstack([draw_utils.draw_tag_edges(p) for p in p_landmarks])
#         #     draw_utils.publish_line_segments('optimized_{:}'.format(landmark_name), edges[:,:3], edges[:,3:6], c='r', 
#         #                                      frame_id='optimized_poses', element_id=pose_id, reset=self.reset_required())

# # Right to left inheritance
# class RobotSLAM(RobotSLAMMixin, GTSAM_BaseSLAM): 
#     def __init__(self, update_on_odom=False, verbose=False, 
#                  odom_noise=GTSAM_VisualSLAM.odom_noise, prior_noise=GTSAM_VisualSLAM.prior_noise, 
#                  visualize_nodes=False, visualize_factors=False, visualize_marginals=False): 
#         GTSAM_BaseSLAM.__init__(self, 
#                                 odom_noise=GTSAM_BaseSLAM.odom_noise, 
#                                 prior_noise=GTSAM_BaseSLAM.prior_noise, verbose=verbose)
#         RobotSLAMMixin.__init__(self, smart=False, landmark_type='pose', 
#                                 update_on_odom=update_on_odom, 
#                                 visualize_nodes=visualize_nodes, 
#                                 visualize_factors=visualize_factors, 
#                                 visualize_marginals=visualize_marginals)
        

# class RobotVisualSLAM(RobotSLAMMixin, GTSAM_VisualSLAM): 
#     def __init__(self, calib, 
#                  min_landmark_obs=3, 
#                  odom_noise=GTSAM_VisualSLAM.odom_noise, prior_noise=GTSAM_VisualSLAM.prior_noise, 
#                  px_error_threshold=4, px_noise=[1.0, 1.0], 
#                  update_on_odom=False, verbose=False, 
#                  visualize_nodes=False, visualize_factors=False, visualize_marginals=False): 
#         GTSAM_VisualSLAM.__init__(self, calib, 
#                                   min_landmark_obs=min_landmark_obs, 
#                                   px_error_threshold=px_error_threshold, 
#                                   odom_noise=odom_noise, prior_noise=prior_noise, 
#                                   px_noise=px_noise, verbose=verbose)
#         RobotSLAMMixin.__init__(self, smart=True, landmark_type='point', 
#                                 update_on_odom=update_on_odom, 
#                                 visualize_nodes=visualize_nodes, 
#                                 visualize_factors=visualize_factors, 
#                                 visualize_marginals=visualize_marginals)


# class TagDetector(object): 
#     def __init__(self, camera, tag_size=0.166): 

#         # Setup camera (identity extrinsics)
#         self.cam_ = camera 

#         # Setup APRILTags detector
#         from pybot_apriltags import AprilTag, AprilTagsWrapper, draw_tags
        
#         self.tag_detector_ = AprilTagsWrapper()
#         self.tag_detector_.set_calib(tag_size=tag_size, fx=camera.fx, fy=camera.fy, cx=camera.cx, cy=camera.cy)

#     def process(self, im):
#         # Detect the tags
#         # im = cam.undistort(to_gray(im))
#         tags = self.tag_detector_.process(to_gray(im), return_poses=True)

#         # Visualize the tags
#         vis = draw_tags(to_color(im), tags)
#         imshow_cv('tag-detector', vis)
#         # self.slam_.draw_tags(vis, tags)
        
#         return tags

