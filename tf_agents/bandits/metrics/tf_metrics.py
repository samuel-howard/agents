# coding=utf-8
# Copyright 2020 The TF-Agents Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""TF metrics for Bandits algorithms.

******** MODIFIED FROM ORIGINAL TO SUPPORT NEW METRICS *********

Have added ExpectedRegretMetric and SuboptimalArmsMetricNew, which caters for
the case when some arms may be identical.

"""

from __future__ import absolute_import
from __future__ import division
# Using Type Annotations.
from __future__ import print_function

from typing import Callable, Optional, Text

import gin
import tensorflow as tf  # pylint: disable=g-explicit-tensorflow-version-import

from tf_agents.bandits.policies import constraints
from tf_agents.bandits.specs import utils as bandit_spec_utils
from tf_agents.metrics import tf_metric
from tf_agents.typing import types
from tf_agents.utils import common

import numpy as np


@gin.configurable
class RegretMetric(tf_metric.TFStepMetric):
  """Computes the regret with respect to a baseline."""

  def __init__(self,
               baseline_reward_fn: Callable[[types.Tensor], types.Tensor],
               name: Optional[Text] = 'RegretMetric',
               dtype: float = tf.float32):
    """Computes the regret with respect to a baseline.

    The regret is computed by computing the difference of the current reward
    from the baseline action reward. The latter is computed by calling the input
    `baseline_reward_fn` function that given a (batched) observation computes
    the baseline action reward.

    Args:
      baseline_reward_fn: function that computes the reward used as a baseline
        for computing the regret.
      name: (str) name of the metric
      dtype: dtype of the metric value.
    """
    self._baseline_reward_fn = baseline_reward_fn
    self.dtype = dtype
    self.regret = common.create_variable(
        initial_value=0, dtype=self.dtype, shape=(), name='regret')
    super(RegretMetric, self).__init__(name=name)

  def call(self, trajectory):
    """Update the regret value.

    Args:
      trajectory: A tf_agents.trajectory.Trajectory

    Returns:
      The arguments, for easy chaining.
    """
    baseline_reward = self._baseline_reward_fn(trajectory.observation)
    trajectory_reward = trajectory.reward
    if isinstance(trajectory.reward, dict):
      trajectory_reward = trajectory.reward[bandit_spec_utils.REWARD_SPEC_KEY]
    trajectory_regret = baseline_reward - trajectory_reward

    #print('trajectory regret:', trajectory_reward)
    self.regret.assign(tf.reduce_mean(trajectory_regret))
    return trajectory

  def result(self):
    return tf.identity(
        self.regret, name=self.name)


@gin.configurable
class ExpectedRegretMetric(tf_metric.TFStepMetric):
  """Computes the expected regret with respect to a baseline."""

  def __init__(self,
               baseline_reward_fn: Callable[[types.Tensor], types.Tensor],
               chosen_reward_fn,#: Callable[[types.Tensor, types.Tensor], types.Tensor],
               name: Optional[Text] = 'RegretMetric',
               dtype: float = tf.float32):
    """Computes the regret with respect to a baseline.

    The expected regret is computed by computing the difference of the
    expectation of the current reward from the baseline action reward. The
    latter is computed by calling the input `baseline_reward_fn` function that
    given a (batched) observation computes the baseline action reward.

    Args:
      baseline_reward_fn: function that computes the reward used as a baseline
        for computing the regret.
      chosen_reward_fn: a function that computes the expectation of the
        current reward
      name: (str) name of the metric
      dtype: dtype of the metric value.
    """
    self._baseline_reward_fn = baseline_reward_fn
    self._chosen_reward_fn = chosen_reward_fn  # Function that calculates the expectated value of the chosen reward
    self.dtype = dtype
    self.regret = common.create_variable(
        initial_value=0, dtype=self.dtype, shape=(), name='regret')
    super(ExpectedRegretMetric, self).__init__(name=name)

  def call(self, trajectory):
    """Update the regret value.

    Args:
      trajectory: A tf_agents.trajectory.Trajectory

    Returns:
      The arguments, for easy chaining.
    """
    #print('action:', trajectory.reward['reward'])#trajectory.action[0], trajectory.action[1])

    baseline_reward = self._baseline_reward_fn(trajectory.observation)
    # This is the largest expected reward of the available actions

    expected_trajectory_reward = self._chosen_reward_fn(trajectory.observation, trajectory.action)
    # This is the expected value of the chosen action

    if isinstance(trajectory.reward, dict):
      trajectory_reward = trajectory.reward[bandit_spec_utils.REWARD_SPEC_KEY]

    expected_trajectory_regret = baseline_reward - expected_trajectory_reward
    # This is the regret that would be expected from choosing the chosen action

    self.regret.assign(tf.reduce_mean(expected_trajectory_regret))
    return trajectory

  def result(self):
    return tf.identity(
        self.regret, name=self.name)


@gin.configurable
class SuboptimalArmsMetric(tf_metric.TFStepMetric):
  """Computes the number of suboptimal arms with respect to a baseline."""

  def __init__(self,
               baseline_action_fn: Callable[[types.Tensor], types.Tensor],
               name: Optional[Text] = 'SuboptimalArmsMetric',
               dtype: float = tf.float32):
    """Computes the number of suboptimal arms with respect to a baseline.

    Args:
      baseline_action_fn: function that computes the action used as a baseline
        for computing the metric.
      name: (str) name of the metric
      dtype: dtype of the metric value.
    """
    self._baseline_action_fn = baseline_action_fn
    self.dtype = dtype
    self.suboptimal_arms = common.create_variable(
        initial_value=0, dtype=self.dtype, shape=(), name='suboptimal_arms')
    super(SuboptimalArmsMetric, self).__init__(name=name)

  def call(self, trajectory):
    """Update the metric value.

    Args:
      trajectory: A tf_agents.trajectory.Trajectory

    Returns:
      The arguments, for easy chaining.
    """
    baseline_action = self._baseline_action_fn(trajectory.observation)
    disagreement = tf.cast(
        tf.not_equal(baseline_action, trajectory.action), tf.float32)
    self.suboptimal_arms.assign(tf.reduce_mean(disagreement))
    return trajectory

  def result(self):
    return tf.identity(
        self.suboptimal_arms, name=self.name)


@gin.configurable
class SuboptimalArmsMetricNew(tf_metric.TFStepMetric):
  """
  Computes the number of suboptimal arms with respect to a baseline,
  corrected for the case when two arms have identical observations
  """

  def __init__(self,
               baseline_action_fn: Callable[[types.Tensor], types.Tensor],
               name: Optional[Text] = 'SuboptimalArmsMetric',
               dtype: float = tf.float32):
    """Computes the number of suboptimal arms with respect to a baseline.

    Args:
      baseline_action_fn: function that computes the action used as a baseline
        for computing the metric.
      name: (str) name of the metric
      dtype: dtype of the metric value.
    """
    self._baseline_action_fn = baseline_action_fn
    self.dtype = dtype
    self.suboptimal_arms = common.create_variable(
        initial_value=0, dtype=self.dtype, shape=(), name='suboptimal_arms')
    super(SuboptimalArmsMetricNew, self).__init__(name=name)

  def call(self, trajectory):
    """Update the metric value.

    Args:
      trajectory: A tf_agents.trajectory.Trajectory

    Returns:
      The arguments, for easy chaining.
    """
    baseline_action_observation = self._baseline_action_fn(trajectory.observation)

    # Find the current observations for the possible actions
    global_obs = trajectory.observation['global']
    per_arm_obs = trajectory.observation['per_arm']
    num_actions = tf.shape(per_arm_obs)[1]
    tiled_global = tf.tile(
        tf.expand_dims(global_obs, axis=1), [1, num_actions, 1])
    concatenated = tf.concat([tiled_global, per_arm_obs], axis=-1)
    #print('print', tf.gather(concatenated, trajectory.action, batch_dims=1))

    # Compare the observation of the action with the largest expected reward
    # with the observation of the chosen action, entry by entry
    disagreement = tf.cast(tf.not_equal(baseline_action_observation,
                        tf.gather(concatenated, trajectory.action, batch_dims=1)),
                        tf.bool)

    #print('disagreement', tf.reduce_any(disagreement, axis = 1))
    # If any entry is different, increase by 1 (as the chosen arm is suboptimal)
    self.suboptimal_arms.assign(tf.reduce_mean(tf.cast(tf.reduce_any(disagreement, axis=1), tf.float32)))
    return trajectory

  def result(self):
    return tf.identity(
        self.suboptimal_arms, name=self.name)


@gin.configurable
class ObsSum(tf_metric.TFStepMetric):
  """
  Computes the number of suboptimal arms with respect to a baseline,
  corrected for the case when two arms have identical observations
  """

  def __init__(self,
               name: Optional[Text] = 'ObsSum',
               dtype: float = tf.float32):
    """Computes the number of suboptimal arms with respect to a baseline.

    Args:
      baseline_action_fn: function that computes the action used as a baseline
        for computing the metric.
      name: (str) name of the metric
      dtype: dtype of the metric value.
    """
    self.dtype = dtype
    self.obs_sum = common.create_variable(
        initial_value=0, dtype=self.dtype, shape=(), name='obs_sum')
    super(ObsSum, self).__init__(name=name)

  def call(self, trajectory):
    """Update the metric value.

    Args:
      trajectory: A tf_agents.trajectory.Trajectory

    Returns:
      The arguments, for easy chaining.
    """
    # Find the current observations for the possible actions
    global_obs = trajectory.observation['global']
    per_arm_obs = trajectory.observation['per_arm']
    num_actions = tf.shape(per_arm_obs)[1]
    tiled_global = tf.tile(
        tf.expand_dims(global_obs, axis=1), [1, num_actions, 1])
    concatenated = tf.concat([tiled_global, per_arm_obs], axis=-1)
    #print('print', tf.gather(concatenated, trajectory.action, batch_dims=1))

    # If any entry is different, increase by 1 (as the chosen arm is suboptimal)
    chosen_obs = tf.gather(concatenated, trajectory.action, batch_dims=1)
    self.obs_sum.assign(tf.reduce_mean(tf.cast(tf.reduce_sum(chosen_obs, axis=1), tf.float32)))
    return trajectory

  def result(self):
    return tf.identity(
        self.obs_sum, name=self.name)


@gin.configurable
class ConstraintViolationsMetric(tf_metric.TFStepMetric):
  """Computes the violations of a certain constraint."""

  def __init__(self,
               constraint: constraints.BaseConstraint,
               name: Optional[Text] = 'ConstraintViolationMetric',
               dtype: float = tf.float32):
    """Computes the constraint violations given an input constraint.

    Given a certain constraint, this metric computes how often the selected
    actions in the trajectory violate the constraint.

    Args:
      constraint: an instance of `tf_agents.bandits.policies.BaseConstraint`.
      name: (str) name of the metric
      dtype: dtype of the metric value.
    """
    self._constraint = constraint
    self.dtype = dtype
    self.constraint_violations = common.create_variable(
        initial_value=0.0,
        dtype=self.dtype,
        shape=(),
        name='constraint_violations')
    super(ConstraintViolationsMetric, self).__init__(name=name)

  def call(self, trajectory):
    """Update the constraint violations metric.

    Args:
      trajectory: A tf_agents.trajectory.Trajectory

    Returns:
      The arguments, for easy chaining.
    """
    feasibility_prob_all_actions = self._constraint(trajectory.observation)
    feasibility_prob_selected_actions = common.index_with_actions(
        feasibility_prob_all_actions,
        tf.cast(trajectory.action, dtype=tf.int32))
    self.constraint_violations.assign(tf.reduce_mean(
        1.0 - feasibility_prob_selected_actions))
    return trajectory

  def result(self):
    return tf.identity(self.constraint_violations, name=self.name)


@gin.configurable
class DistanceFromGreedyMetric(tf_metric.TFStepMetric):
  """Difference between the estimated reward of the chosen and the best action.

  This metric measures how 'safely' the agent explores: it calculates the
  difference between what the agent thinks it would have gotten had it chosen
  the best looking action, vs the action it actually took. This metric is not
  equivalent to the regret, because the regret is calculated as a distance from
  optimality, while here everything calculated is based on the policy's
  'belief'.
  """

  def __init__(self,
               estimated_reward_fn: Callable[[types.Tensor], types.Tensor],
               name: Optional[Text] = 'DistanceFromGreedyMetric',
               dtype: float = tf.float32):
    """Init function for the metric.

    Args:
      estimated_reward_fn: A function that takes the observation as input and
        computes the estimated rewards that the greedy policy uses.
      name: (str) name of the metric
      dtype: dtype of the metric value.
    """
    self._estimated_reward_fn = estimated_reward_fn
    self.dtype = dtype
    self.safe_explore = common.create_variable(
        initial_value=0, dtype=self.dtype, shape=(), name='safe_explore')
    super(DistanceFromGreedyMetric, self).__init__(name=name)

  def call(self, trajectory):
    """Update the metric value.

    Args:
      trajectory: A tf_agents.trajectory.Trajectory

    Returns:
      The arguments, for easy chaining.
    """
    all_estimated_rewards = self._estimated_reward_fn(trajectory.observation)
    max_estimated_rewards = tf.reduce_max(all_estimated_rewards, axis=-1)
    estimated_action_rewards = tf.gather(
        all_estimated_rewards, trajectory.action, batch_dims=1)
    self.safe_explore.assign(
        tf.reduce_mean(max_estimated_rewards - estimated_action_rewards))
    return trajectory

  def result(self):
    return tf.identity(self.safe_explore, name=self.name)
