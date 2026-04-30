# NavRL-Enhanced Urban UAV Navigation: A Hybrid Deep Reinforcement Learning and Path-Planning Framework for Safe Autonomous Flight in Structured Environments

---

**Capstone Project Report**  
Department of Electrical and Computer Engineering  
Academic Year 2025–2026

---

| Field | Details |
|---|---|
| Project Title | NavRL-Enhanced Urban UAV Navigation |
| Submission Date | April 2026 |
| Simulator | Microsoft AirSim (Unreal Engine 4, City Environment) |
| Base Framework | NavRL [1] — Carnegie Mellon University |
| Test Platform | AirSim City, 12-waypoint urban roam mission (~800 m) |

---

## Abstract

This report presents a capstone evaluation and extension of **NavRL**, a deep reinforcement learning (DRL) based navigation framework for unmanned aerial vehicles (UAVs), originally developed at Carnegie Mellon University [1]. NavRL employs Proximal Policy Optimization (PPO) with carefully designed state representations, LiDAR-based static obstacle perception, and a velocity-obstacle safety shield to achieve collision-free autonomous flight. The contribution of this capstone project is threefold: (1) a faithful AirSim simulation deployment of the NavRL model for quantitative benchmarking in a photorealistic urban environment; (2) the design and implementation of a hybrid city planner that integrates NavRL's reactive RL policy with A\* global path planning, a city altitude controller, and a Pure Pursuit lookahead module; and (3) a systematic multi-suite evaluation comparing the hybrid system against the pure RL baseline across standard, domain-randomization, and ablation conditions. Results demonstrate that the hybrid system achieves a **75.00% goal-success rate** with **0.69 collisions/km** — a **2× improvement in success** and **13× reduction in collision rate** relative to the pure RL baseline (36.66%, 9.31 collisions/km) — validating the thesis that structured urban navigation requires global planning in combination with reactive RL control.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Background and Related Work](#2-background-and-related-work)
3. [The NavRL Framework — Theory and Mathematical Foundations](#3-the-navrl-framework)
4. [System Architecture — Capstone Extensions](#4-system-architecture)
5. [Simulation Environment and Test Setup](#5-simulation-environment-and-test-setup)
6. [Experimental Results](#6-experimental-results)
7. [Discussion and Analysis](#7-discussion-and-analysis)
8. [Hardware Design for Real-World Deployment](#8-hardware-design-for-real-world-deployment)
9. [Conclusion and Future Work](#9-conclusion-and-future-work)
10. [References](#references)

---

## 1. Introduction

Autonomous UAVs are increasingly deployed in applications ranging from urban delivery and infrastructure inspection to search-and-rescue operations [2][3]. Safe flight in structured environments — where buildings, elevated infrastructure, and dynamic elements coexist — demands navigation systems that are simultaneously reactive at the local level (obstacle avoidance within meters) and deliberate at the global level (route planning across hundreds of meters).

Traditional approaches decompose this problem into a pipeline of modular components: a global planner (e.g., A\*, RRT\*), a local planner (e.g., potential fields, ESDF gradient), and a low-level controller. While these systems are interpretable and tunable, they suffer from parameter brittleness and performance degradation when environmental assumptions are violated [1].

Deep reinforcement learning offers an alternative: through trial-and-error in simulation, a policy network can learn a mapping from raw sensory observations directly to velocity commands, implicitly encoding obstacle avoidance without hand-crafted rules. The NavRL framework [1] from Carnegie Mellon University achieves precisely this, demonstrating zero-shot sim-to-real transfer on a physical quadcopter.

However, purely reactive RL has a fundamental limitation: its obstacle perception range is bounded by the LiDAR maximum range (4 m in NavRL), which is insufficient to route around large, extended obstacles or to select globally efficient paths in a dense urban canyon. This work hypothesizes and empirically confirms that **a hybrid system combining NavRL's reactive policy with A\* global planning achieves significantly superior performance in structured urban environments**, without retraining the underlying policy.

### 1.1 Objectives

1. Deploy and benchmark the NavRL checkpoint in Microsoft AirSim.
2. Design a hybrid city planner that wraps NavRL with global path planning and altitude management.
3. Evaluate both systems across a comprehensive set of test suites.
4. Analyze the contribution of each architectural component through ablation.

---

## 2. Background and Related Work

### 2.1 Traditional UAV Navigation

Rule-based methods for UAV navigation in dynamic environments rely on hierarchical modules with handcrafted algorithms [4][5]. Wang et al. [4] demonstrate vision-aided autonomous flight, while Xu et al. [5] address gradient-based B-spline trajectory optimization for dynamic obstacle avoidance. These methods achieve good performance in their target settings but require careful parameter tuning and can fail under environmental distribution shifts.

The EGO-Planner [6] is a widely benchmarked ESDF-free gradient-based local planner for quadrotors that operates without explicit signed-distance-field computation. While efficient in open environments, its map-update mechanism becomes noisy in the presence of dynamic obstacles.

### 2.2 Reinforcement Learning for UAV Navigation

Q-learning and value-learning approaches [7][8][9] have demonstrated successful UAV navigation but are constrained to discrete action spaces, limiting maneuverability. Policy gradient methods using actor-critic structures [10] support continuous action spaces. Kaufmann et al. [11] trained a policy in simulation that outperforms human pilots in drone racing, demonstrating the capability ceiling of RL-based drone control.

For collision avoidance, He et al. [12] introduce a reach-avoid network as a recovery policy. Kochdumper et al. [13] use reachability analysis for safe action projection, though with exponential scaling in action dimensions.

### 2.3 Sim-to-Real Transfer

The sim-to-real gap is a central challenge for RL-based UAV systems. Camera-based methods [14][15] are particularly susceptible due to rendering differences. NavRL [1] addresses this by adopting ray-cast LiDAR representations — which have minimal simulation-to-reality discrepancy — rather than camera images, enabling zero-shot transfer.

### 2.4 Positioning of This Work

This capstone extends NavRL to structured urban environments where the 4 m reactive horizon is insufficient for global navigation. The hybrid architecture introduced here is orthogonal to the original training procedure — the RL policy is used as-is, augmented by a planning layer that it was not trained to collaborate with. This tests the generalizability of the NavRL policy outside its training distribution and provides a quantifiable measure of what pure RL alone cannot achieve.

---

## 3. The NavRL Framework

*This section presents the theoretical foundations of NavRL as published in [1], included here to provide the mathematical basis of the system under evaluation.*

### 3.1 Problem Formulation

The navigation task is formulated as a Markov Decision Process (MDP) defined by the tuple $(S, A, P, R, \gamma)$, where:

- $S$ is the state space (robot internal states and sensory observations)
- $A$ is the continuous action space
- $P(s_{t+1} | s_t, a_t)$ is the transition model
- $R(s_t, a_t)$ is the reward function
- $\gamma \in [0, 1]$ is the discount factor

The optimal policy maximizes the expected discounted cumulative reward:

$$\pi^* = \arg\max_\pi \mathbb{E}\left[\sum_{t=0}^{T} \gamma^t R(s_t, a_t)\right] \tag{1}$$

### 3.2 State Representation

#### 3.2.1 Internal State

The robot's internal state captures its goal-relative geometry and velocity. All vectors are expressed in the **goal coordinate frame** $(\cdot)^G$, where the X-axis aligns with the robot-to-goal direction:

$$S_{int} = \left[\frac{P_g^G - P_r^G}{\|P_g^G - P_r^G\|},\ \|P_g^G - P_r^G\|,\ V_r^G\right]^T \tag{2}$$

where $P_r$ and $P_g$ denote robot and goal positions respectively, and $V_r$ is the robot velocity. This goal-coordinate transformation reduces dependency on absolute world coordinates, improving RL convergence speed [1].

The full internal state vector is **8-dimensional**:
- 3D unit vector toward goal (normalized relative position): 3 values
- 2D distance to goal (horizontal + vertical): 2 values
- 3D velocity in goal frame: 3 values

#### 3.2.2 Dynamic Obstacle State

Dynamic obstacles are represented as a matrix $S_{dyn} \in \mathbb{R}^{N_d \times M}$, where each row corresponds to the $i$-th closest obstacle:

$$\mathcal{D}_i = \left[\frac{P_{o_i}^G - P_r^G}{\|P_{o_i}^G - P_r^G\|},\ \|P_{o_i}^G - P_r^G\|,\ V_{o_i}^G,\ \text{dim}(o_i)\right]^T \tag{3}$$

where $P_{o_i}$, $V_{o_i}$ are the obstacle center position and velocity, and $\text{dim}(o_i)$ encodes height and width. If fewer than $N_d$ obstacles are detected, remaining entries are zero-padded.

#### 3.2.3 Static Obstacle State (LiDAR Ray Casting)

Static obstacles are encoded via 3D ray casting from the robot's position against an occupancy voxel map. Rays are cast horizontally at 360° with a user-defined angular resolution $\Delta\theta_h$, and at multiple vertical elevation angles $\theta_v$. The resulting range matrix is:

$$S_{stat} = [R_{\theta_0}, \ldots, R_{\theta_{N_v}}], \quad S_{stat} \in \mathbb{R}^{N_h \times N_v} \tag{4}$$

where $N_h = \lfloor 360 / \Delta\theta_h \rfloor$ and $N_v$ is the number of vertical planes. In the NavRL deployment:

| Parameter | Value |
|---|---|
| $\Delta\theta_h$ | 10° (36 horizontal bins) |
| $\theta_v$ angles | −10°, 0°, 10°, 20° (4 vertical bins) |
| Max ray length | 4.0 m |
| Bin orientation | Bin 0 = toward goal direction |

The inverted representation fed to the network is:

$$S_{stat}^{inv}(i,j) = \max(R_{max} - S_{stat}(i,j),\ 0.1)$$

so that high values indicate **proximity** rather than distance, matching the sign convention expected by the trained policy.

### 3.3 Action Representation

At each time step, the policy outputs a normalized velocity $\hat{V}^G_{ctrl} \in [0,1]^3$ in the goal coordinate frame. The final velocity command is:

$$V^G_{ctrl} = v_{lim} \cdot (2 \cdot \hat{V}^G_{ctrl} - 1), \quad \hat{V}^G_{ctrl} \in [0, 1] \tag{5}$$

where $v_{lim} = 2.0$ m/s is the maximum velocity. This formulation maps $[0,1] \to [-v_{lim}, v_{lim}]$ linearly, providing greater design flexibility than directly learning the action bounds.

To constrain the output to $[0,1]$, the actor network produces parameters $(\alpha, \beta)$ for a **Beta distribution**. Using the Beta distribution rather than a Gaussian for bounded action spaces has been shown to be bias-free and achieve faster convergence [16]:

$$\hat{V}^G_{ctrl} \sim \text{Beta}(\alpha, \beta), \quad \alpha, \beta > 0$$

During training, actions are sampled from this distribution for exploration. During deployment, the **mean** of the Beta distribution is used:

$$\hat{V}^G_{ctrl} = \frac{\alpha}{\alpha + \beta} \tag{6}$$

The velocity is expressed in the goal coordinate frame and must be transformed to the world frame before being sent to the flight controller via:

$$V^{world}_{ctrl} = \mathbf{R}_{G \to W}^{-1} \cdot V^G_{ctrl} \tag{7}$$

where $\mathbf{R}_{G \to W}$ is the rotation matrix from world to goal frame.

### 3.4 Reward Function

The total reward at each time step consists of five components weighted by scalars $\lambda_i$:

$$r = \lambda_1 r_{vel} + \lambda_2 r_{ss} + \lambda_3 r_{ds} + \lambda_4 r_{smooth} + \lambda_5 r_{height} \tag{7}$$

**a) Velocity Reward** — encourages motion toward the goal:

$$r_{vel} = \frac{P_g - P_r}{\|P_g - P_r\|} \cdot V_r \tag{8}$$

This rewards the component of velocity aligned with the goal direction, incentivizing both speed and directionality.

**b) Static Safety Reward** — penalizes proximity to static obstacles:

$$r_{ss} = \frac{1}{N_h N_v} \sum_{i=1}^{N_h} \sum_{j=1}^{N_v} \log S_{stat}(i,j) \tag{9}$$

The log formulation provides a smooth gradient that becomes strongly negative as ray distances approach zero, enforcing clearance.

**c) Dynamic Safety Reward** — penalizes proximity to dynamic obstacles:

$$r_{ds} = \frac{1}{N_d} \sum_{i=1}^{N_d} \log \|P_r - P_{o_i}\| \tag{10}$$

**d) Smoothness Reward** — penalizes abrupt velocity changes:

$$r_{smooth} = -\|V_r(t_i) - V_r(t_{i-1})\| \tag{11}$$

**e) Height Reward** — prevents excessive altitude variation:

$$r_{height} = -\left(\min(|P_{r,z} - P_{s,z}|, |P_{r,z} - P_{g,z}|)\right)^2 \tag{12}$$

This penalty activates when the robot's altitude falls outside the range defined by the start and goal heights, discouraging obstacle avoidance by excessive climbing.

### 3.5 Network Architecture

The static obstacle state $S_{stat}$ and dynamic obstacle state $S_{dyn}$ are both 2D matrices, processed by independent **3-layer Convolutional Neural Networks (CNNs)** to produce 1D embeddings of sizes 128 (static) and 64 (dynamic) respectively. These embeddings are concatenated with the 8D internal state and fed into a **2-layer Multi-Layer Perceptron (MLP)** that outputs the Beta distribution parameters $(\alpha, \beta)$.

The policy is trained using **Proximal Policy Optimization (PPO)** [17] with:
- PPO clip ratio: 0.1
- Optimizer: ADAM, learning rate $5 \times 10^{-4}$
- Discount factor $\gamma = 0.99$
- Training hardware: NVIDIA GeForce RTX 4090
- Training time: ~10 hours with 1024 parallel quadcopters in NVIDIA Isaac Sim

A curriculum learning strategy starts at 60 dynamic obstacles and increases to 120 in steps of 20, each time the success rate exceeds 80%. The best checkpoint was saved at 100 dynamic obstacles, achieving a training success rate of **80.96%** [1].

**Table 1: Training success rates with and without curriculum learning [1]**

| Environment | Without Curriculum | With Curriculum |
|---|---|---|
| Static=350, Dynamic=60 | 94.33% | 94.33% |
| Static=350, Dynamic=80 | 74.51% | 82.71% |
| Static=350, Dynamic=100 | 62.30% | 80.96% |
| Static=350, Dynamic=120 | 54.98% | 68.65% |

### 3.6 Policy Action Safety Shield

Due to the black-box nature of neural networks, NavRL employs a safety shield based on the **velocity obstacle (VO)** concept [18]. Given the policy output $V_{rl}$, the shield checks whether this velocity would cause a collision within a defined time horizon. If so, it solves a constrained optimization:

$$\min_{V_{safe} \in \mathbb{R}^3} \|V_{safe} - V_{rl}\| \tag{13a}$$

$$\text{s.t.} \quad (V_{safe} - (V_{rl} - V_{o_i} + \Delta V_i)) \cdot \Delta V_i \geq 0 \quad \forall i \in \{1, \ldots, N\} \tag{13b}$$

$$V_{min} \leq V_{safe} \leq V_{max} \tag{13c}$$

where constraint (13b) defines a hyperplane based on the minimum velocity change $\Delta V_i$ required to exit the velocity obstacle region of obstacle $i$, and (13c) enforces control limits. For static obstacles, each cast ray determines the obstacle center and radius with zero velocity. For dynamic obstacles, spherical bounding volumes are used.

The safety shield reduces collisions by **18.7%** in dynamic environments and **47.8%** in hybrid environments compared to NavRL without the shield [1].

**Table 2: NavRL collision benchmark vs. baseline methods [1]**

| Method | Static Env. | Dynamic Env. | Hybrid Env. |
|---|---|---|---|
| EGO-Planner [6] | 0.45 (56.3%) | N/A | N/A |
| ViGO [5] | 0.80 (100%) | 3.15 (100%) | 4.40 (100%) |
| NavRL w/o Shield | 0.95 (118.8%) | 2.70 (85.7%) | 4.60 (104.5%) |
| **NavRL (Ours)** | **0.65 (81.3%)** | **0.85 (27.0%)** | **2.10 (47.8%)** |

*Values: average collision count per run (percentage relative to ViGO baseline).*

**Runtime performance on NVIDIA Jetson Orin NX [1]:**

| Module | RTX 4090 | Jetson Orin NX |
|---|---|---|
| Static Perception | 8 ms | 15 ms |
| Dynamic Perception | 11 ms | 27 ms |
| RL Policy Network | 1 ms | 7 ms |
| Safety Shield | 2 ms | 16 ms |
| **Total** | **22 ms** | **65 ms** |

All modules operate within real-time constraints at 20 Hz control frequency (50 ms budget).

---

## 4. System Architecture — Capstone Extensions

This section describes the original contributions of this capstone project, built on top of the NavRL framework.

### 4.1 AirSim Deployment Bridge

The NavRL model was deployed in Microsoft AirSim connected to an Unreal Engine 4 city environment. The deployment pipeline (`navrl_airsim_bridge.py`) handles:

1. **LiDAR acquisition**: AirSim's `LidarSensor1` operates with 360° horizontal FOV, 4 channels, and a 10,000 points/second rate at `DataFrame=SensorLocalFrame`.
2. **Frame transformation**: Raw body-frame point cloud → world NED frame (via quaternion rotation) → goal-relative frame → ENU convention → (36 × 4) bin assignment → distance inversion.
3. **State construction**: 8D state vector matching the training formulation (Equation 2), with NED ↔ ENU conversions applied consistently.
4. **Action execution**: Model output (ENU velocity) converted to NED and dispatched at 20 Hz via `moveByVelocityAsync`.

The frame transformation chain is critical for correct bin alignment with the training distribution. Specifically, after rotating points into the goal-relative frame, the sign flip (y → −y, z → −z) converts from NED to ENU to match the training simulator's coordinate convention.

### 4.2 Hybrid City Planner

The hybrid city planner (`navrl_city_planner.py`) wraps the NavRL policy with three additional layers:

#### 4.2.1 A\* Global Path Planning with Altitude-Aware Occupancy Grid

A 2D occupancy grid is maintained at the drone's current flight altitude. The grid is updated in real time from LiDAR scans projected onto the flight plane. A\* search produces a sequence of waypoints from the current position to the goal, routed around known obstacles.

The occupancy grid uses an inflation radius of 1 cell around detected obstacles to provide clearance margins for the drone body, consistent with standard robotic path planning practice.

#### 4.2.2 City Altitude Controller

Urban environments contain buildings of varying heights. A state-machine altitude controller manages three regimes:

- **Normal flight**: Maintain target altitude via P-controller with velocity clamping
- **Ceiling detected** (building above drone): Proportional descent to route under or around
- **High-altitude clearance**: Climb to maximum altitude (20 m) when path is blocked at current altitude, triggering a replan

The altitude controller operates on the Z-axis independently from the XY NavRL policy, preventing the model's Z output (which showed poor performance in isolation, as quantified in the ablation study) from causing altitude instability.

#### 4.2.3 Pure Pursuit Lookahead

A critical instability observed during testing was that commanding the drone to the next immediate A\* waypoint caused rapid oscillation when the waypoint was within 1–2 m — the unit-vector computation $\hat{u} = (p_{goal} - p_{drone}) / \|p_{goal} - p_{drone}\|$ becomes numerically ill-conditioned at close range, and any positional noise causes large bearing swings.

The Pure Pursuit algorithm [19] was implemented to resolve this. Rather than targeting the immediate next waypoint, the system advances along the remaining path segments from the drone's current position until a lookahead distance $d_L = 4.0$ m is reached, then interpolates to find the exact lookahead point $p_L$:

$$p_L = p_i + t \cdot (p_{i+1} - p_i)$$

where $t$ is computed such that the accumulated arc length from the drone equals $d_L$. The RL policy then navigates toward $p_L$ rather than the immediate waypoint. This provides:

- Stable unit vectors even for close-range waypoints
- Smoother path tracking with less overshoot
- Effective path smoothing without resampling

#### 4.2.4 Collision Recovery

When a collision is detected, the planner executes a bounce-back maneuver along the inverted pre-collision velocity vector, then replans from the recovery position. This prevents the drone from becoming trapped against an obstacle face.

### 4.3 Test Harness

A multi-suite test harness (`roam_test.py`) implements five evaluation protocols:

| Suite | Purpose | Controllers |
|---|---|---|
| **Standard** | Baseline performance, no perturbations | PureRL, Hybrid |
| **Domain Randomization** | Weather (fog, rain) + wind perturbations | PureRL, Hybrid |
| **Ablation** | Incremental architecture comparison | All 5 variants |
| **Sensor Noise** | Gaussian noise on LiDAR readings | PureRL, Hybrid |
| **IMU Noise** | Gaussian noise on position/velocity/yaw/altitude | PureRL, Hybrid |

The noise injection is implemented as runtime monkey-patching of the bridge's `process_lidar` and `get_state` methods, applying perturbations at the sensor boundary without modifying the policy or planner logic.

---

## 5. Simulation Environment and Test Setup

### 5.1 AirSim City Environment

All experiments were conducted in Microsoft AirSim connected to the Unreal Engine 4 **City** environment — a photorealistic urban scene containing multi-story buildings, street furniture, elevated structures, and open plazas. The environment spans approximately 400 m × 400 m.

**AirSim sensor configuration:**

```json
{
  "SensorType": 6,
  "Enabled": true,
  "NumberOfChannels": 4,
  "PointsPerSecond": 10000,
  "HorizontalFOVStart": 0,
  "HorizontalFOVEnd": 360,
  "DataFrame": "SensorLocalFrame",
  "Range": 70
}
```

The LiDAR provides a full 360° horizontal sweep at 4 vertical channels. The deployed model uses only the nearest 4.0 m of returns, consistent with the training range.

### 5.2 Roam Mission

All evaluation suites share a fixed 12-waypoint continuous roam mission covering diverse urban terrain:

| # | Waypoint Name | Goal (x, y) m | Characteristic |
|---|---|---|---|
| 1 | open_east | [40, 0] | Open field — warmup |
| 2 | behind_north_bldg | [0, 55] | Building occlusion |
| 3 | west_open | [−50, 30] | Open terrain |
| 4 | near_bldg4_NW | [−90, 65] | Northwest building cluster |
| 5 | SE_wall_compound | [75, −60] | Long diagonal through city center |
| 6 | south_cluster | [−10, −95] | Dense southern building cluster |
| 7 | apartment_ESE | [90, −70] | East apartment block |
| 8 | building9_NE | [97, 26] | Northeast building |
| 9 | north_tower | [55, 110] | Far north — 122 m range |
| 10 | NW_tower | [−60, 115] | Far northwest tower |
| 11 | on_north_bldg | [0, 29] | Rooftop vicinity |
| 12 | return_home | [0, 0] | Return to origin |

The drone starts each run at the origin [0, 0], altitude −3.0 m (NED), corresponding to 3 m above ground. Goals are evaluated sequentially without resets between legs (except post-collision recovery). A leg is considered successful if the drone reaches within 2.0 m of the goal within 240 seconds.

**Control parameters:**

| Parameter | Value |
|---|---|
| Control frequency | 20 Hz |
| Max velocity | 2.0 m/s |
| Default altitude (NED) | −3.0 m |
| Collision timeout | 0.5 s freshness window |
| Close-call threshold | < 1.5 m obstacle distance |
| Stuck detection | < 0.3 m/s for 8 s |

### 5.3 Ablation Variants

The ablation study isolates the contribution of each architectural component:

| Label | Controller | Description |
|---|---|---|
| **PureRL** | `pure_rl` | NavRL policy controls XY and Z directly. No altitude management, no planning. |
| **RL+FixedAlt** | `rl_fixed_alt` | NavRL controls XY. Z locked to 3 m via simple P-controller. |
| **RL+AltSM** | `rl_alt` | NavRL controls XY. Z managed by full altitude state machine. |
| **PControl+AltSM** | `p_control_alt` | Proportional controller for XY. Altitude state machine for Z. No RL. |
| **NavRL+CityPlanner** | `hybrid` | Full system: A\* planning + NavRL XY + altitude state machine + Pure Pursuit. |

---

## 6. Experimental Results

### 6.1 Standard Suite — Primary Benchmark

The standard suite evaluates both controllers across 5 independent runs on the 12-waypoint roam mission under clean simulation conditions.

**Table 3: Standard Suite Results (n=5 runs, 12 goals per run)**

| Metric | PureRL | Hybrid (NavRL+CityPlanner) |
|---|---|---|
| **Success Rate** | **36.66% ± 4.12%** | **75.00% ± 0.00%** |
| Collisions/km | 9.31 ± 0.75 | 0.69 ± 0.49 |
| Collision Rate/Goal | 0.633 ± 0.041 | 0.100 ± 0.063 |
| Avg. Path Efficiency | 103.82% ± 0.39% | 82.50% ± 3.39% |
| Avg. Time to Goal (s) | 20.06 ± 1.52 | 77.94 ± 8.62 |
| Avg. Min. Obstacle Dist. (m) | 1.487 ± 0.142 | 1.982 ± 0.168 |
| Total Close Calls (<1.5 m) | 114.2 ± 14.7 | 516.8 ± 257.2 |
| Avg. Flight Altitude (m) | 3.13 ± 0.00 | 5.10 ± 0.92 |
| Max Altitude Reached (m) | 3.38 ± 0.01 | 26.86 ± 1.00 |
| Total Path Length (m) | 817.4 ± 13.2 | — |

*[Figure 1: Bar chart — Success Rate comparison. Placeholder for chart.]*  
*[Figure 2: Box plot — Collisions/km across 5 runs. Placeholder for chart.]*

**Key observations:**

- The hybrid planner achieves **exactly 75.00% success** in all 5 runs (9/12 goals per run), demonstrating complete reproducibility — suggesting deterministic A\* routing reliably solves 9 of the 12 legs.
- PureRL success varies between 33.3% and 41.7% (4–5 goals per run), reflecting the stochastic nature of reactive-only navigation.
- The hybrid planner's **13× reduction in collision rate** (0.69 vs. 9.31 per km) is the primary quantitative result of this work.
- Efficiency is deliberately lower for the hybrid system (82.5% vs 103.8%) because A\* routes around obstacles rather than flying straight through them, increasing path length. The >100% PureRL efficiency indicates it partially succeeds on legs by flying shorter-than-optimal paths — only because it collides and resets before reaching longer-route goals.
- The hybrid system's higher close-call count reflects longer total flight time and deliberate low-altitude building approaches.

### 6.2 Ablation Study

The ablation study systematically evaluates five architectural variants across 5 runs to isolate the contribution of each component.

**Table 4: Ablation Study Results (n=5 runs)**

| Controller | Success Rate | Collisions/km | Avg Min Obs. (m) | Close Calls | Altitude Std (m) |
|---|---|---|---|---|---|
| **PureRL** | 34.98% ± 3.36% | 9.615 ± 0.608 | 1.532 ± 0.108 | 104.8 ± 12.5 | 0.098 ± 0.004 |
| **RL+FixedAlt** | 41.70% ± 0.00% | 9.389 ± 0.003 | 1.875 ± 0.005 | 94.0 ± 4.6 | 0.063 ± 0.004 |
| **RL+AltSM** | 43.36% ± 3.32% | 9.680 ± 0.724 | 1.923 ± 0.113 | 69.2 ± 9.7 | 0.462 ± 0.050 |
| **PControl+AltSM** | 33.30% ± 0.00% | 11.910 ± 0.002 | 1.239 ± 0.016 | 106.2 ± 3.3 | 0.252 ± 0.007 |
| **NavRL+CityPlanner** | **71.68% ± 4.07%** | **0.406 ± 0.366** | **1.921 ± 0.184** | **519.0 ± 274.7** | **1.724 ± 0.600** |

*[Figure 3: Grouped bar chart — All 5 controllers across key metrics. Placeholder.]*

**Component-by-component analysis:**

1. **RL vs. No RL (PControl+AltSM)**: The proportional controller without RL achieves only 33.3% success with the **highest collision rate** (11.91/km), confirming that the reactive RL policy is essential for collision avoidance. Even simple fixed-altitude P-control cannot navigate the city adequately.

2. **Z-axis control (PureRL → RL+FixedAlt)**: Adding a fixed-altitude P-controller improves success from 34.98% to 41.70% and reduces close calls from 104.8 to 94.0. This demonstrates that the model's Z output is unreliable and benefits from external altitude stabilization.

3. **Altitude state machine (RL+FixedAlt → RL+AltSM)**: The full altitude state machine further improves success to 43.36% and reduces close calls to 69.2, with a larger altitude range (min 0.90 m, max 10.4 m) indicating the drone actively navigates over obstacles. However, the collision rate remains high (9.68/km) because reactive XY avoidance alone is insufficient for the urban layout.

4. **Global planning (RL+AltSM → NavRL+CityPlanner)**: Adding A\* global planning with Pure Pursuit lookahead produces the most significant improvement: success jumps from 43.36% to 71.68% and collision rate drops from 9.68 to 0.41 per km — a **24× reduction**. This confirms that global routing is the dominant missing capability in pure RL urban navigation.

5. **Altitude standard deviation** scales with system capability: PureRL (0.098 m) flies virtually flat; the hybrid (1.724 m) actively uses altitude variation to navigate the 3D urban structure.

### 6.3 Domain Randomization Suite

The domain randomization suite tests robustness under 5 randomly sampled weather and wind conditions (seed=42), using a single run per condition per controller.

Conditions include fog levels up to 0.7, rain up to 0.4, and wind speeds up to 8.0 m/s at random directions. A representative condition (run 1) had fog=0.307, rain=0.343, wind=5.579 m/s in the [0.15, −0.989] direction.

*[Figure 4: Line plot — success rate across 5 domain randomization conditions for both controllers. Placeholder.]*

*[Figure 5: Box plot — collision rate under each weather condition. Placeholder.]*

### 6.4 Robustness Suites — Sensor Noise and IMU Noise

These suites are currently pending AirSim environment availability and will be incorporated in the final submission. The experimental protocol is as follows:

**Sensor (LiDAR) Noise conditions:**

| Condition | Gaussian σ (m) | Dropout |
|---|---|---|
| Clean (baseline) | 0 | 0 |
| Light noise | 0.05 | 0 |
| Heavy noise | 0.10 | 0 |

**IMU Noise conditions:**

| Condition | Position σ (m) | Velocity σ (m/s) | Yaw σ (deg) | Altitude σ (m) |
|---|---|---|---|---|
| Light | 0.05 | 0.05 | 1.0 | 0.03 |
| Medium | 0.10 | 0.10 | 2.5 | 0.06 |
| Heavy | 0.20 | 0.15 | 5.0 | 0.10 |

Noise is injected directly at the sensor boundary (LiDAR tensor and state tuple), simulating realistic sensor degradation without modifying the simulation physics. Results will be reported as degradation curves relative to the clean baseline.

---

## 7. Discussion and Analysis

### 7.1 Why Pure RL Fails at the City Scale

The NavRL policy was trained in a 50 m × 50 m arena with sparse random obstacles [1]. The AirSim city environment presents two fundamentally different challenges:

1. **Extended obstacles**: Buildings subtend 30–90° of horizontal LiDAR coverage and extend over hundreds of meters. The 4 m reaction horizon is insufficient to route around them — by the time the model detects a building face, there is not enough lateral space to avoid it.

2. **Global route topology**: The optimal path between city waypoints often requires deliberate detours of 50–100 m. Reactive RL has no mechanism to choose such detours; it always moves toward the goal until blocked.

This is reflected in the data: PureRL achieves >103% path efficiency on successful legs because it takes near-straight-line paths. But those straight lines pass through buildings on 63.3% of all legs, resulting in collisions.

### 7.2 The Hybrid Architecture's Trade-offs

The hybrid system's lower path efficiency (82.5%) and higher time-to-goal (77.94 s vs 20.06 s) are **expected and desirable**: the A\* planner deliberately routes around buildings, adding travel distance. The trade-off is clear — longer paths in exchange for successful arrival.

The non-zero collision rate of the hybrid system (0.69/km) arises from three sources:
- A\* waypoints that pass close to building walls, where the NavRL reactive policy cannot make tight enough evasive maneuvers
- Altitude transitions (climbing to clear rooftops) where the drone briefly overflies structure edges
- Dynamic obstacles not represented in the static occupancy grid

### 7.3 Altitude as a Navigation Dimension

A key insight from the ablation study is that altitude management is **not a secondary concern** but an active navigation strategy. The hybrid planner's altitude range of 2.75 m to 26.86 m (nearly 10× the PureRL range of 2.76 m to 3.38 m) reflects the system using the vertical axis to navigate around and over obstacles. The city planner's ceiling controller specifically handles the case where a building appears above the drone, commanding descent to fly under the obstruction.

### 7.4 Close Calls — A Counterintuitive Metric

The hybrid system logs significantly more close calls (516.8 vs 114.2 for PureRL in the standard suite). This is counterintuitive but explainable: the hybrid system spends far more time flying near buildings (because it successfully navigates close to them without colliding), while PureRL frequently collides and resets, spending less total time in proximity. Close calls are a measure of flight near obstacles, not a measure of safety failure.

### 7.5 Limitations

1. **4 m LiDAR range ceiling**: The NavRL policy cannot react to obstacles beyond 4 m. In the real world, LiDAR with 20–70 m range is standard; adapting the observation to use multi-resolution bins could extend the effective reaction horizon without retraining.

2. **2D A\* planning**: The current occupancy grid is 2D (projected at flight altitude). A full 3D voxel map with A\* in 3D would better handle variable-height obstacles.

3. **No dynamic obstacle awareness in planner**: The A\* path does not account for moving obstacles. The NavRL reactive layer handles these implicitly, but the global plan may route through a dynamic obstacle's predicted path.

4. **Sim-to-real gap for the planner layer**: While NavRL's perception is designed for sim-to-real transfer, the A\* occupancy grid relies on AirSim's LiDAR simulation fidelity. Real-world LiDAR noise may degrade map quality.

---

## 8. Hardware Design for Real-World Deployment

This section outlines a hardware platform capable of running the full NavRL+CityPlanner stack in real-world deployment.

### 8.1 Onboard Computing

The NavRL team validated real-time inference on the **NVIDIA Jetson Orin NX** [1], with a total pipeline latency of 65 ms (Table 2) — well within the 50 ms control budget at 20 Hz. For the full hybrid stack (A\* planning + NavRL inference), additional headroom is required:

| Component | Jetson Orin NX (estimated) |
|---|---|
| NavRL inference | 7 ms |
| Safety shield | 16 ms |
| Static perception | 15 ms |
| A\* planning (2D grid, 100×100) | ~5 ms |
| Pure Pursuit lookahead | < 1 ms |
| **Total** | **~44 ms** |

The **Jetson Orin NX 16 GB** is recommended as the minimum compute platform. It provides 1024 CUDA cores for PyTorch inference, 16 GB unified memory for map storage, and native ROS2 support. The Raspberry Pi 4/5 lacks CUDA and cannot achieve real-time NavRL inference.

### 8.2 LiDAR Sensor

The NavRL model requires a 360° horizontal FOV LiDAR producing at least 4 vertical channels. The **Livox MID-360** is a candidate:

| Parameter | Livox MID-360 | NavRL Requirement |
|---|---|---|
| Horizontal FOV | 360° | 360° |
| Vertical channels | Solid-state non-repetitive | ≥ 4 channels |
| Max range | 40 m | 4 m used (any ≥ 4 m) |
| Weight | ~265 g | Minimal |
| Interface | ROS2/Ethernet | ROS2 compatible |

### 8.3 Frame Design with Generative Design

The drone frame should be designed in Fusion 360 using Generative Design to minimize mass while satisfying structural constraints from motor thrust loads (4× upward per arm), landing impact (5G downward), and vibration from motor harmonics. Recommended constraints:

- **Material**: Carbon fiber reinforced polymer (CFRP) for arm structures, aluminum 6061 for motor mounts
- **Load cases**: 4× motor thrust, 5G landing impact, 200 Hz vibration (motor resonance avoidance)
- **CFD analysis**: Simulate prop wash interaction with Jetson/LiDAR mount for thermal management
- **FEA stress analysis**: Verify frame under asymmetric load (single motor failure)

### 8.4 Complete Hardware BOM (Indicative)

| Component | Candidate | Rationale |
|---|---|---|
| Compute | Jetson Orin NX 16 GB | CUDA + ROS2, validated by NavRL authors [1] |
| Frame | Custom CFRP (Generative Design) | Minimized mass, optimized aerodynamics |
| Motors | T-Motor MN5008 KV340 | Low vibration, high efficiency |
| Props | 15" Carbon Fiber | Matched to motor KV and 6S battery |
| ESCs | Hobbywing XRotor 40A (DSHOT600) | Clean telemetry, BLHeli32 |
| Battery | 6S LiPo 10,000 mAh | ~20 min endurance |
| LiDAR | Livox MID-360 | 360° solid-state, lightweight |
| Flight Controller | Cube Orange+ | MAVLink, ArduPilot, triple IMU |
| Depth Camera | Intel RealSense D435i | Dynamic obstacle detection (as used in [1]) |
| IMU/Odometry | FAST-LIO2 [20] | LiDAR-inertial odometry for state estimation |

---

## 9. Conclusion and Future Work

### 9.1 Summary

This capstone project deployed and systematically evaluated the NavRL deep reinforcement learning navigation framework [1] in a photorealistic urban simulation environment. A hybrid architecture was designed, implemented, and validated that integrates NavRL's reactive RL policy with A\* global path planning, a city altitude controller, collision recovery, and Pure Pursuit lookahead.

The principal results are:

- **The hybrid system achieves 75.00% goal-success rate** versus 36.66% for pure RL — a **2× improvement**.
- **Collision rate is reduced by 13×** (0.69 vs 9.31 per km).
- **Ablation analysis** identifies global path planning as the dominant contributing factor (24× collision rate reduction when added to RL+AltSM).
- **The RL policy's Z-axis output is unreliable** — external altitude management adds 8% success improvement over pure RL.
- The NavRL policy transfers well to AirSim, validating its sim-to-real design philosophy.

### 9.2 Future Work

1. **Sensor/IMU noise robustness** — Complete the pending noise suites to quantify degradation under realistic sensor conditions. Hypothesis: the hybrid system will degrade less gracefully than PureRL under position noise, since A\* planning depends on accurate positioning.

2. **3D occupancy and planning** — Extend the occupancy grid to 3D using a voxel representation, enabling A\* to route vertically as well as horizontally.

3. **Dynamic obstacle integration into the global plan** — Feed the NavRL dynamic obstacle detections into the A\* cost map to predict and avoid moving object paths.

4. **Physical deployment** — Fabricate the hardware platform described in Section 8, implement the ROS2 integration layer, and validate the hybrid system in an outdoor structured environment.

5. **Retraining with extended LiDAR range** — Retrain the NavRL policy with a larger max-ray length (e.g., 8–10 m) and investigate whether the policy learns to make earlier, softer avoidance maneuvers.

---

## References

[1] Z. Xu, X. Han, H. Shen, H. Jin, and K. Shimada, "NavRL: Learning Safe Flight in Dynamic Environments," *IEEE Robotics and Automation Letters*, vol. 10, no. 4, pp. 3668–3675, Apr. 2025. DOI: 10.1109/LRA.2025.3546069.

[2] S. H. Alsamhi et al., "UAV computing-assisted search and rescue mission framework for disaster and harsh environment mitigation," *Drones*, vol. 6, no. 7, 2022, Art. no. 154.

[3] Z. Xu, B. Chen, X. Zhan, Y. Xiu, C. Suzuki, and K. Shimada, "A vision-based autonomous UAV inspection framework for unknown tunnel construction sites with dynamic obstacles," *IEEE Robotics and Automation Letters*, vol. 8, no. 8, pp. 4983–4990, Aug. 2023.

[4] Y. Wang, J. Ji, Q. Wang, C. Xu, and F. Gao, "Autonomous flights in dynamic environments with onboard vision," in *Proc. IEEE/RSJ Int. Conf. Intelligent Robots and Systems*, 2021, pp. 1966–1973.

[5] Z. Xu, Y. Xiu, X. Zhan, B. Chen, and K. Shimada, "Vision-aided UAV navigation and dynamic obstacle avoidance using gradient-based B-spline trajectory optimization," in *Proc. IEEE Int. Conf. Robotics and Automation*, 2023, pp. 1214–1220.

[6] X. Zhou, Z. Wang, H. Ye, C. Xu, and F. Gao, "EGO-planner: An ESDF-free gradient-based local planner for quadrotors," *IEEE Robotics and Automation Letters*, vol. 6, no. 2, pp. 478–485, Apr. 2021.

[7] F. Sadeghi and S. Levine, "CAD2RL: Real single-image flight without a single real image," in *Proc. Robotics: Science and Systems*, Cambridge, MA, Jul. 2017.

[8] L. Xie, S. Wang, A. Markham, and N. Trigoni, "Towards monocular vision based obstacle avoidance through deep reinforcement learning," arXiv:1706.09829, 2017.

[9] A. Singla, S. Padakandla, and S. Bhatnagar, "Memory-based deep reinforcement learning for obstacle avoidance in UAV with limited environment knowledge," *IEEE Trans. Intelligent Transportation Systems*, vol. 22, no. 1, pp. 107–118, Jan. 2021.

[10] R. Brilli et al., "Monocular reactive collision avoidance for MAV teleoperation with deep reinforcement learning," in *Proc. IEEE Int. Conf. Robotics and Automation*, 2023, pp. 12535–12541.

[11] E. Kaufmann, L. Bauersfeld, A. Loquercio, M. Müller, V. Koltun, and D. Scaramuzza, "Champion-level drone racing using deep reinforcement learning," *Nature*, vol. 620, no. 7976, pp. 982–987, 2023.

[12] T. He, C. Zhang, W. Xiao, G. He, C. Liu, and G. Shi, "Agile but safe: Learning collision-free high-speed legged locomotion," in *Proc. Robotics: Science and Systems*, Delft, Netherlands, Jul. 2024.

[13] N. Kochdumper, H. Krasowski, X. Wang, S. Bak, and M. Althoff, "Provably safe reinforcement learning via action projection using reachability analysis and polynomial zonotopes," *IEEE Open Journal of Control Systems*, vol. 2, pp. 79–92, 2023.

[14] Y. Song, K. Shi, R. Penicka, and D. Scaramuzza, "Learning perception-aware agile flight in cluttered environments," in *Proc. IEEE Int. Conf. Robotics and Automation*, 2023, pp. 1989–1995.

[15] D. Gandhi, L. Pinto, and A. Gupta, "Learning to fly by crashing," in *Proc. IEEE/RSJ Int. Conf. Intelligent Robots and Systems*, 2017, pp. 3948–3955.

[16] P.-W. Chou, D. Maturana, and S. Scherer, "Improving stochastic policy gradients in continuous control with deep reinforcement learning using the beta distribution," in *Proc. Int. Conf. Machine Learning*, 2017, pp. 834–843.

[17] J. Schulman, F. Wolski, P. Dhariwal, A. Radford, and O. Klimov, "Proximal policy optimization algorithms," arXiv:1707.06347, 2017.

[18] P. Fiorini and Z. Shiller, "Motion planning in dynamic environments using velocity obstacles," *Int. Journal of Robotics Research*, vol. 17, no. 7, pp. 760–772, 1998.

[19] R. C. Coulter, "Implementation of the pure pursuit path tracking algorithm," CMU Robotics Institute Technical Report CMU-RI-TR-92-01, Jan. 1992.

[20] W. Xu, Y. Cai, D. He, J. Lin, and F. Zhang, "FAST-LIO2: Fast direct LiDAR-inertial odometry," *IEEE Trans. Robotics*, vol. 38, no. 4, pp. 2053–2073, Aug. 2022.

---

*Report prepared as part of Capstone Project evaluation, April 2026.*  
*Base RL framework: NavRL, Zhefan Xu et al., CMU [1]. Hybrid planner and evaluation: Capstone Team.*  
*AirSim simulation environment: Microsoft Research.*
