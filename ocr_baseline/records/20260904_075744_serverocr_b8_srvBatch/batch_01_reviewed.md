# 一维束缚态

当 $V_0 \to 0$ 时，能量本征方程 $\hat{H}\psi = E\psi$ 在坐标表象中表达为：

$$\left[-\frac{\hbar^2}{2m}\frac{d^2}{dx^2} + V(x)\right]\psi(x) = E\psi(x)$$

在一维情况下，$\hat{H}\psi = E\psi$ 简化为：

$$\left(-\frac{\hbar^2}{2m}\frac{d^2}{dx^2} + V(x)\right)\psi(x) = E\psi(x)$$

## 定理1（势函数不连续时）

设 $V(x) = \begin{cases} V_1, & x < a \\ V_2, & x \ge a \end{cases}$，在 $x=a$ 处不连续，有一个跳跃。当 $V_1 - V_2$ 有限时，能量本征函数 $\psi(x)$ 及其导函数 $\psi'(x) = \frac{d\psi}{dx}$ 在 $a$ 点是连续的。

$\psi(x)$ 本身连续是因为概率幅的连续性问题（$\psi(x)$ 是概率波！!!）

**思路1：** $\int \psi''(x)dx = \psi'(a+\varepsilon) - \psi'(a-\varepsilon) = \int [V(x) - E]\psi(x)dx$，$|\psi(x)| < \infty$，$\varepsilon \to 0$ 时右式 $\to 0$

**思路2：** 反证法，若 $\psi(x)$ 不连续，则 $\psi''(x)$ 含冲击项，不符合薛定谔方程

**思路3：** 由 $\frac{\partial \rho(x,t)}{\partial t} + \nabla \cdot \vec{j}(x,t) = 0$，$\rho = \psi^*\psi = |\psi|^2$，$\vec{j} = -\frac{i\hbar}{2m}(\psi^*\nabla\psi - \psi\nabla\psi^*)$。由 $\rho$ 连续 $\Rightarrow \psi, \psi^*$ 连续

## 一维半无限深方势阱

$$V(x) = \begin{cases} \infty, & x < 0 \\ 0, & 0 < x < a \\ V_0, & x > a \end{cases}$$

$$-\frac{\hbar^2}{2m}\psi''(x) + V(x)\psi(x) = E\psi(x)$$

**$x < 0$ 区域：** $V(x) = \infty$，则物理上不允许粒子在此区域出现，故有 $\psi(x) = 0 \quad (x < 0)$

**$0 < x < a$ 区域：** 有 $\psi''(x) + k^2\psi(x) = 0$，其中 $k^2 = \frac{2mE}{\hbar^2}$，$k = \frac{\sqrt{2mE}}{\hbar}$。由 $\psi(0) = 0$，则 $\psi(x) = A\sin kx$

**$x > a$ 区域：** 有 $\psi''(x) - \frac{2m(V_0 - E)}{\hbar^2}\psi(x) = 0$。令 $\beta^2 = \frac{2m(V_0 - E)}{\hbar^2}$，则 $\psi(x) = Be^{-\beta x} + Ce^{\beta x}$

$\because \psi(x) \xrightarrow{x \to \infty} 0$，若 $\beta$ 为虚数即 $V_0 < E$，$\psi(x)$ 周期振荡不满足束缚态，故仅考虑 $\beta$ 为实数且 $> 0$。

$x \to \infty$ 时 $e^{\beta x} \to \infty$，$\therefore C = 0$，$\psi(x) = Be^{-\beta x}$

$$\psi(a) = Be^{-\beta a} = A\sin ka, \quad \psi'(a) = -\beta Be^{-\beta a} = Ak\cos ka$$

于是有 $k\cot ka = -\beta = -\sqrt{\frac{2m(V_0 - E)}{\hbar^2}}$，$E = V_0 \sin^2 ka = \frac{V_0}{2}[1 - \cos(2ka)]$

且 $\cot ka < 0$。$\Rightarrow E$ 满足超越方程 $E = \frac{V_0}{2}[1 - \cos(2ka)]$ 且 $\cot(ka) < 0$。**能级是量子化的**

$E \ll V_0$ 时，$\cos(2ka) \approx -1$，$E = E_j = \left(j + \frac{1}{2}\right)^2 \frac{\pi^2\hbar^2}{2ma^2} > E_1$

归一化：$\int_0^\infty |\psi(x)|^2 dx = \int_0^a A^2\sin^2 kx\, dx + A^2\sin^2 ka \int_a^\infty e^{-2\beta(x-a)} dx = A^2\left(\frac{a}{2} + \frac{\sin^2 ka}{2\beta}\right) = 1$

---

# 气体的基本统计规律

- 中科技大学
- ONG UNIVERSITY OF SCIENCE AND TECHNOLOGY

## 气体的微观模型

$$PV = \nu RT = \frac{N}{N_A}RT = NkT$$

$$P = \frac{N}{V}kT = nkT, \quad n \text{为单位体积内的粒子数}$$

标准状态下的气体分子数密度 $n_0 = 2.69 \times 10^{25} \text{ m}^{-3}$，表示每 $\text{m}^3$ 理想气体中的微观粒子数。

分子线度为 $d$，则 $d^3 \sim \frac{V}{N_A} = \frac{1}{n_0}$，$d \sim \sqrt[3]{\frac{1}{n_0}}$，即可不计分子本身的大小。

**理想气体的微观模型：**
1. 可不计分子本身的大小
2. 除碰撞外，气体分子间及气体分子同器壁间的相互作用可忽略
3. 分子在两次碰撞间做匀速直线运动

**压强的微观模型：**
1. 宏观上认为器壁受连续作用力
2. 热平衡时，假设分子和器壁的碰撞是弹性碰撞
3. 分子混沌性假设：平衡态时，气体分子的热运动速度无择优方向

第 $i$ 个分子与 $A_1$ 碰撞，$y, z$ 分量不变，$x$ 方向速度分量由 $v_{xi} \to -v_{xi}$。

第 $i$ 个分子单位时间与 $A_1$ 碰撞次数为 $\frac{v_{xi}}{2L}$，单位时间单位面积冲量即压强。

$$P = \frac{1}{V}\sum_i (2mv_{xi}^2) = \frac{N}{V}m\overline{v_x^2} = nm\overline{v_x^2}$$

由 $\overline{v_x^2} = \frac{1}{3}\overline{v^2}$，则 $P = \frac{1}{3}nm\overline{v^2} = \frac{2}{3}n\overline{\varepsilon_k}$

$\varepsilon_k = \frac{1}{2}m\overline{v^2}$ 为粒子的平均动能。$\because P = \frac{2}{3}n\overline{\varepsilon_k} = nkT \Rightarrow \overline{\varepsilon_k} = \frac{3}{2}kT$

## 分子的平均动能与理想气体系统的内能

只考虑分子平动动能，$U = \sum_i \varepsilon_i = N\overline{\varepsilon_k} = \frac{3}{2}NkT = \frac{3}{2}\nu RT$

定体热容 $C_V = \left(\frac{\partial U}{\partial T}\right)_V = \frac{3}{2}\nu R$，$C_{V,m} = \frac{3}{2}R$

---

# 近独立粒子系的麦克斯韦-玻尔兹曼分布能量分布律

## 微观粒子基本运动状态的经典描述（能量、坐标、动量）

### 自由平动粒子

在三维空间中运动时，粒子的自由度为 3，位置由 $x, y, z$ 标定，与之共轭的动量为 $p_x = m\dot{x}$，$p_y = m\dot{y}$，$p_z = m\dot{z}$，$\dot{x}$ 表示 $x$ 对时间的导数。

无外力作用时，$E = \frac{1}{2m}(p_x^2 + p_y^2 + p_z^2)$。粒子状态可由 $x, y, z, p_x, p_y, p_z$ 确定。

### 线性谐振子

质量为 $m$ 的粒子在弹性力 $F = -Ax$ 作用下在平衡点附近作简谐运动，振动圆频率 $\omega = \sqrt{\frac{A}{m}}$。

$$E = \frac{p^2}{2m} + \frac{1}{2}Ax^2 = \frac{p^2}{2m} + \frac{1}{2}m\omega^2 x^2 = \text{常数}$$

以 $x, p$ 为直角坐标可构成二维 $\mu$ 空间，若 $E$ 给定，则代表点的轨迹是椭圆，椭圆面积 $S = \pi\sqrt{2mE} \cdot \sqrt{\frac{2E}{m\omega^2}} = \frac{2\pi E}{\omega}$

即 $S = \frac{E}{\nu}$（$\nu$ 为振动频率）。

### 转子（双原子分子整体刚性转动）

考虑质量为 $m$ 的质点 $A$ 被具有一定长度的轻杆系于原点时所做运动（$r$ 一定）。

$$E = \frac{1}{2}m(\dot{x}^2 + \dot{y}^2 + \dot{z}^2), \quad x = r\sin\theta\cos\varphi, \quad y = r\sin\theta\sin\varphi, \quad z = r\cos\theta$$

$$E = \frac{1}{2}m(r^2\dot{\theta}^2 + r^2\sin^2\theta\dot{\varphi}^2) = \frac{1}{2}mr^2(\dot{\theta}^2 + \sin^2\theta\dot{\varphi}^2)$$

对于双原子分子，两质点绕系统质心转动可约化为质量为 $\mu$ 的单体转动问题。

$\mu = \frac{m_1 m_2}{m_1 + m_2}$。取质心为坐标原点，$m_1$ 原子距原点 $r_1$，$m_2$ 原子距原点 $r_2$。

$$r_1 = \frac{m_2}{m_1 + m_2}r, \quad r_2 = \frac{m_1}{m_1 + m_2}r$$

$I_{\text{总}} = m_1 r_1^2 + m_2 r_2^2 = \mu r^2$。系统转动能量 $T_{\text{转}} = \frac{1}{2}m_1 r_1^2(\dot{\theta}^2 + \sin^2\theta\dot{\varphi}^2) + \frac{1}{2}m_2 r_2^2(\dot{\theta}^2 + \sin^2\theta\dot{\varphi}^2)$

即 $T_{\text{转}} = \frac{1}{2}\mu r^2(\dot{\theta}^2 + \sin^2\theta\dot{\varphi}^2) = \frac{1}{2}I(\dot{\theta}^2 + \sin^2\theta\dot{\varphi}^2) = \frac{p_\theta^2}{2I} + \frac{p_\varphi^2}{2I\sin^2\theta}$

$p_\theta = \mu r^2\dot{\theta} = I\dot{\theta}$，$p_\varphi = \mu r^2\sin^2\theta\dot{\varphi} = I\sin^2\theta\dot{\varphi}$（与 $\theta, \varphi$ 共轭的动量）

$$T_{\text{总}} = \frac{1}{2I}\left(p_\theta^2 + \frac{p_\varphi^2}{\sin^2\theta}\right)$$

## 宏观分布、组态、微观态

### $\mu$ 空间分割（宏观）

把 $\mu$ 空间分成许多小体元 $\Delta\omega_j (j = 1, 2, \ldots, l)$，$\Delta\omega_j$ 大小适当，足够小到可近似认为代表点落在 $\Delta\omega_j$ 内的粒子运动状态相同，但也不是无穷小，要满足 $\Delta\omega_j \ge h^r$（统计需要）。

### 宏观分布与宏观态（与 $\mu$ 空间的分布 $\{a_j\}$ 对应）

宏观状态参量是相应微观物理量的统计平均值。

知道了 $\Delta\omega_j (j = 1, 2, \ldots, l)$ 体元内代表点的数目 $a_j (j = 1, 2, \ldots, l)$，即可确定系统的内能等宏观量的平均值，从而系统的宏观态也就确定了。

### 宏观分布的组态（配容）（哪些粒子的代表点在 $\Delta\omega_j$ 内）

经典力学中，粒子是可分辨的，交换两粒子的状态会改变系统的状态（微观）。

一个宏观分布 $\{a_j\}$ 对应的组态数 $W = \frac{N!}{\prod_j a_j!}$，即将 $N$ 个粒子按 $\{a_j\}$ 分布给 $l$ 个状态的可能数。

### 经典力学中一个组态的微观数（相字 $\Delta\omega_j \to$ 相格 $h_0^r$，过渡到微观）

粒子的状态是连续的，粒子和系统的微观运动状态不可数 $\Rightarrow$ 人为划出最小的"格子"。

将 $p_i, q_i$ 分为等间隔区域，$\delta p_i \delta q_i = h_0 \Rightarrow (\delta q_1 \delta p_1) \cdots (\delta q_r \delta p_r) = h_0^r$，相格 $h_0^r$ 代表一个粒子态。

$\mu$ 相字空间小体元 $\Delta\omega_j (j = 1, 2, \ldots, l)$ 中粒子运动状态数为 $\Delta w_j = \frac{\Delta\omega_j}{h_0^r}$，$a_j$ 个粒子在 $\Delta w_j$ 个运动状态上分布的可能微观状态数为 $\binom{a_j + \Delta w_j - 1}{a_j}$，多个粒子可以处于同一相格内。

### 一个分布的微观分布数

$$\Omega = \prod_j \binom{a_j + \Delta w_j - 1}{a_j} = \prod_j \frac{(a_j + \Delta w_j - 1)!}{a_j!(\Delta w_j - 1)!}$$

## 等概率原理和最概然统计

若系统的各微观态无更多限制，就假定一切符合所有约束条件的微观态出现的概率相等。

**最概然统计：** 认为出现概率最大（即微观态数最多）的那个宏观态分布对应于系统的平衡态。

## 最概然分布求算

一个宏观态分布 $\{a_j\}$ 出现的微观态数为 $\Omega$，则 $\Omega$ 最大也即 $\ln\Omega$ 最大，$\delta(\ln\Omega) = 0$（即 $d(\ln\Omega) = 0$）。

$$\Omega = \prod_j \frac{(a_j + \Delta w_j - 1)!}{a_j!(\Delta w_j - 1)!}, \quad \ln\Omega = \ln N! - \sum_j \ln a_j! + \sum_j a_j \ln(\Delta w_j)$$

$$\delta\ln\Omega = \delta\ln N! - \sum_j \delta\ln a_j! + \sum_j \ln(\Delta w_j) \cdot \delta a_j = \sum_j [-\ln a_j + \ln(\Delta w_j)]\delta a_j = 0$$

由斯特林公式，$M$ 足够大时，有 $\ln M! \approx M\ln M - M$。

则 $\sum_j \delta(a_j\ln a_j - a_j) - \sum_j \ln(\Delta w_j)\delta a_j = \sum_j (\ln a_j \delta a_j + \delta a_j - \delta a_j) - \sum_j \ln(\Delta w_j)\delta a_j = \sum_j (\ln a_j - \ln\Delta w_j)\delta a_j = 0$

又有粒子数和能量守恒条件（孤立系），则 $\sum_j \delta a_j = 0$，$\sum_j E_j \delta a_j = 0$。

令 $f(a_1, a_2, \ldots, a_l, \alpha, \beta) = \sum_j [-a_j(\ln a_j - 1) - \ln(\Delta w_j)a_j] + \alpha(\sum_j a_j - N) + \beta(\sum_j E_j a_j - E)$

则 $f$ 取极值时，$\frac{\partial f}{\partial a_j} = 0$，$\frac{\partial f}{\partial \alpha} = \frac{\partial f}{\partial \beta} = 0$。$\ln a_j + \alpha + \beta E_j = 0$。

$$a_j = \Delta w_j e^{-\alpha - \beta E_j}$$

且此时 $f$ 取极大值。

$\beta = -\frac{1}{kT}$，是一个普遍量，$a_j = \Delta w_j e^{-\alpha - \beta E_j}$。

由 $\sum_j a_j = N$，则 $e^{-\alpha}\sum_j \Delta w_j e^{-\beta E_j} = N$。引入配分函数 $Z = \sum_j \Delta w_j e^{-\beta E_j}$，则 $e^{-\alpha} = \frac{N}{Z}$。

## MB 分布的物理意义

**MB 分布是出现概率最大的一种分布**，别的分布出现的概率可忽略，MB 分布给出了系统处于平衡态时同一时刻系统内粒子取某一能量值的概率。

**宏观态与微观态的关系：**

- 宏观态 $\to$ $\mu$ 空间的分布 $\{a_j\}$
- $\Delta\omega_j$ 可继续细分 $\to$ 一种分布有多种实现方法
- 多个组态 $\to$ 一个组态有多种微观态

---

## $\Delta\omega$ 的分割举例

二维线性谐振子 $E = \frac{p^2}{2m} + \frac{1}{2}m\omega^2 x^2$，$\frac{p^2}{2mE} + \frac{x^2}{2E/(m\omega^2)} = 1$，代表点的轨迹为椭圆（$\mu$ 空间）。

$$S = \frac{2\pi E}{\omega} = \Delta\omega$$

$\Delta\omega = h$ 时，$\Delta\omega = h$。

**偏离最概然分布的概率很小**，平衡态对应的微观态数为 $W^*$，最概然分布附近一个分布对应的微观态数为 $W$。假设 $N = 2n$ 个粒子处在一个体积 $V$ 的空间中，将 $V$ 等体积划分为 $\Delta\omega_1, \Delta\omega_2$。

$$W^* = \binom{2n}{n}, \quad W = \binom{2n}{n + \delta n}, \quad \frac{W}{W^*} = \frac{(n!)^2}{(n + \delta n)!(n - \delta n)!}, \quad \ln\left(\frac{W}{W^*}\right) \approx -\frac{2\delta n^2}{n}, \quad n \text{很大}，\to 0$$

## 量子态中的 $\mu$ 空间

$\Delta X \Delta P_x \ge \frac{\hbar}{2}$，一个粒子的代表不再是点，而是一团"小空间"。粒子的状态是分立的，不再需要用"$\mu$ 空间"，只需考虑分立能级上的分布即可。

三维平动子能级 $E_{n_x, n_y, n_z} = \frac{\hbar^2\pi^2}{2m}\left(\frac{n_x^2}{L_x^2} + \frac{n_y^2}{L_y^2} + \frac{n_z^2}{L_z^2}\right)$

刚性转子能级 $E_l = \frac{\hbar^2}{2I}l(l+1)$，$[l(l+1) = 2I\omega]$

谐振子能级 $E_n = \left(n + \frac{1}{2}\right)\hbar\omega$

平动子能级间隔极小，可视为连续分布，按 $de$ 分能级；常温下，转动也可看作连续（不含 $H_2$）；振动一般必须看作分立能级，直接分析量子能级简并度。

## 量子态与相空间体积之间的对应关系

对于一个自由度为 $r$ 的粒子，它的 $\mu$ 空间中大小为 $h^r$ 的相体积对应一个量子态。

**三维平动子：** $E = \frac{1}{2m}(p_x^2 + p_y^2 + p_z^2)$，$0 \sim E$ 范围内的总量子态数 $\Sigma(E) = \frac{4\pi}{3}\frac{(2mE)^{3/2}}{h^3}V = \frac{4\pi V}{3h^3}(2mE)^{3/2}$（第一象限）

**双原子分子刚性转子：** $E = \frac{1}{2I}\left(p_\theta^2 + \frac{p_\varphi^2}{\sin^2\theta}\right)$，$I = \mu r^2$

令 $p_\theta = \sqrt{2IE}\cos\gamma$，$p_\varphi = \sqrt{2IE}\sin\theta \cdot \sin\gamma$，$dp_\theta dp_\varphi = \left|\begin{matrix} -\sqrt{2IE}\sin\gamma & 0 \\ \sqrt{2IE}\sin\theta\cos\gamma & \sqrt{2IE}\sin\theta\sin\gamma \end{matrix}\right| d\gamma d\theta = 2IE\sin\theta\, d\theta\, d\gamma$

$$\Sigma(E) = \frac{1}{h^2}\int dp_\theta \int \sin\theta\, d\theta \int d\gamma \cdot I \int dE = \frac{8\pi^2 IE}{h^2}$$

（四维：$\theta, \varphi, p_\theta, p_\varphi$；$0 < \theta < \pi, 0 < \varphi < 2\pi, 0 < \gamma < 2\pi$）

---

# 算符与狄拉克符号

## 狄拉克符号

$|\psi\rangle$：右矢；$\langle\psi|$：左矢，称 $|\psi\rangle$ 或 $\langle\psi|$ 为态矢，$\psi$ 是一个标签，用于区分不同的量子态。

$\langle\psi| = (|\psi\rangle)^\dagger$，左矢与右矢是一种共轭转置关系。$\langle\psi|a = a\langle\psi|$（$a$ 为复数）。

内积：$(\varphi, \psi) = \langle\varphi|\psi\rangle$，坐标表象 $\int \varphi^*(\vec{r})\psi(\vec{r}) d\tau$，$d\tau = dxdydz$ 为微体积元，$\psi(\vec{r}) = \psi(x, y, z)$。

$\langle\varphi|\psi\rangle^* = \langle\psi|\varphi\rangle$，用定积分理解是共轭，用矩阵理解是转置后取共轭。

**正交：** $\langle\varphi|\psi\rangle = 0$ 代表 $\varphi$ 和 $\psi$ 是正交的；**归一：** $\langle\psi|\psi\rangle = 1$ 代表 $\psi$ 是归一化的。

**平均值：** 力学量 $A$ 在归一化量子态 $\psi$ 下的平均值 $\bar{A} = \langle\psi|\hat{A}|\psi\rangle$。

$|\psi\rangle, \langle\psi|$ 是量子态 $\psi$ 在右矢、左矢空间的不同表示。

## 左、右矢空间的算符运算

设 $\hat{A}$ 和 $\hat{B}$ 是两个算符，$\forall |\psi\rangle$ 和 $|\varphi\rangle$，若 $\langle\varphi|\hat{A}|\psi\rangle = \langle\varphi|\hat{B}|\psi\rangle$，则称 $\hat{B}$ 为 $\hat{A}$ 的转置算符。

$|\varphi\rangle = \hat{A}|\psi\rangle$，在右矢空间中，$|\varphi\rangle = \hat{A}|\psi\rangle = |\hat{A}\psi\rangle$，默认 $\hat{A}$ 向右作用；在左矢空间中，$\langle\varphi| = \langle\psi|\hat{A}^\dagger$，算符 $\hat{A}^\dagger (\hat{A}^*)$ 向左作用。$\langle\varphi|\hat{A}^T = \langle\hat{A}\varphi| = \langle\varphi|$。若 $\hat{A}$ 为厄米算符，则 $\langle\varphi| = \langle\psi|\hat{A}$。

$\Rightarrow$ **厄米算符在左、右矢空间中的运算具有形式不变性。**

算符在左矢和右矢之间的转换本质上是对偶空间的伴随映射。

关于 $(\langle\psi|\hat{A}|\psi\rangle)^* = \langle\psi|\hat{A}^\dagger|\psi\rangle$：$\bar{A} = \langle\psi|\hat{A}|\psi\rangle$，$\bar{A}^* = \langle\psi|\hat{A}^\dagger|\psi\rangle$，$\bar{A} = \langle\psi|\hat{A}|\psi\rangle^* = \langle\hat{A}\psi|\psi\rangle \Rightarrow \langle\hat{A}\psi| = \langle\psi|\hat{A}^\dagger$。

$\langle\psi|\hat{A}\hat{B}|\varphi\rangle = \langle\psi|\hat{B}^\dagger\hat{A}^\dagger|\varphi\rangle$（先将 $\hat{B}\varphi$ 视为一体，再作变换）。

## 基矢与本征方程

F14>＝入14)，称（4＞为算符户的本征态，入为本征值．

$\hat{F}|\psi\rangle = \lambda|\psi\rangle$，称 $|\psi\rangle$ 为算符 $\hat{F}$ 的本征态，$\lambda$ 为本征值。

能量本征方程：$\hat{H}|k\rangle = E_k|k\rangle$，将 $|k\rangle$ 简记为 $|k\rangle$（为基矢），量子数 $k$ 标记系统所有量子数。

## 角动量的对易式

$\hat{\vec{L}} = \hat{\vec{r}} \times \hat{\vec{p}}$，$\hat{L}_x = \hat{y}\hat{p}_z - \hat{z}\hat{p}_y = -i\hbar\left(y\frac{\partial}{\partial z} - z\frac{\partial}{\partial y}\right)$

$\hat{L}_y = -i\hbar\left(z\frac{\partial}{\partial x} - x\frac{\partial}{\partial z}\right) = \hat{z}\hat{p}_x - \hat{x}\hat{p}_z$

$\hat{L}_z = -i\hbar\left(x\frac{\partial}{\partial y} - y\frac{\partial}{\partial x}\right) = \hat{x}\hat{p}_y - \hat{y}\hat{p}_x$

$[\hat{L}_x, \hat{x}] = [\hat{y}\hat{p}_z - \hat{z}\hat{p}_y, \hat{x}] = 0$，$[\hat{L}_\alpha, \hat{x}] = 0 \quad (\alpha = x, y, z)$

$[\hat{L}_x, \hat{y}] = [\hat{y}\hat{p}_z, \hat{y}] - [\hat{z}\hat{p}_y, \hat{y}] = -[\hat{z}\hat{p}_y, \hat{y}] = i\hbar\hat{z}$

$[\hat{L}_x, \hat{z}] = [\hat{y}\hat{p}_z - \hat{z}\hat{p}_y, \hat{z}] = [\hat{y}\hat{p}_z, \hat{z}] = -i\hbar\hat{y}$（或 $\hat{L}_x\hat{z} = -i\hbar\hat{y}$）

同理有 $[\hat{L}_y, \hat{x}] = -i\hbar\hat{z}$，$[\hat{L}_y, \hat{z}] = i\hbar\hat{x}$，$[\hat{L}_z, \hat{x}] = i\hbar\hat{y}$，$[\hat{L}_z, \hat{y}] = -i\hbar\hat{x}$。

$[\hat{L}_x, \hat{p}_x] = [\hat{y}\hat{p}_z - \hat{z}\hat{p}_y, \hat{p}_x] = 0$，$[\hat{L}_\alpha, \hat{p}_\alpha] = 0 \quad (\alpha = x, y, z)$

$[\hat{L}_x, \hat{p}_y] = [\hat{y}\hat{p}_z - \hat{z}\hat{p}_y, \hat{p}_y] = [\hat{y}\hat{p}_z, \hat{p}_y] = \hat{p}_z[\hat{y}, \hat{p}_y] = i\hbar\hat{p}_z$

$[\hat{L}_x, \hat{p}_z] = [\hat{y}\hat{p}_z - \hat{z}\hat{p}_y, \hat{p}_z] = -[\hat{z}\hat{p}_y, \hat{p}_z] = -\hat{p}_y[\hat{z}, \hat{p}_z] = -i\hbar\hat{p}_y$

同理有 $[\hat{L}_y, \hat{p}_x] = -i\hbar\hat{p}_z$，$[\hat{L}_y, \hat{p}_z] = i\hbar\hat{p}_x$，$[\hat{L}_z, \hat{p}_x] = i\hbar\hat{p}_y$，$[\hat{L}_z, \hat{p}_y] = -i\hbar\hat{p}_x$。

$[\hat{L}_x, \hat{L}_x] = 0$，$[\hat{L}_\alpha, \hat{L}_\alpha] = 0 \quad (\alpha = x, y, z)$

$[\hat{L}_x, \hat{L}_y] = [\hat{y}\hat{p}_z - \hat{z}\hat{p}_y, \hat{z}\hat{p}_x - \hat{x}\hat{p}_z] = [\hat{y}\hat{p}_z, \hat{z}\hat{p}_x] - [\hat{y}\hat{p}_z, \hat{x}\hat{p}_z] - [\hat{z}\hat{p}_y, \hat{z}\hat{p}_x] + [\hat{z}\hat{p}_y, \hat{x}\hat{p}_z]$

$= [\hat{y}\hat{p}_z, \hat{z}\hat{p}_x] + [\hat{z}\hat{p}_y, \hat{x}\hat{p}_z] = \hat{y}[\hat{p}_z, \hat{z}]\hat{p}_x + \hat{x}[\hat{z}, \hat{p}_z]\hat{p}_y = -i\hbar(\hat{y}\hat{p}_x) - i\hbar(\hat{x}\hat{p}_y) = i\hbar\hat{L}_z$

同理，$[\hat{L}_y, \hat{L}_z] = i\hbar\hat{L}_x$，$[\hat{L}_z, \hat{L}_x] = i\hbar\hat{L}_y$。

令 $\hat{L}^2 = \hat{L}_x^2 + \hat{L}_y^2 + \hat{L}_z^2$，$\hat{L}_x = \hat{y}\hat{p}_z - \hat{z}\hat{p}_y$，$\hat{L}_y = \hat{z}\hat{p}_x - \hat{x}\hat{p}_z$，$\hat{L}_z = \hat{x}\hat{p}_y - \hat{y}\hat{p}_x$。

则 $\hat{L}^2 = (y^2 + z^2)\hat{p}_x^2 + (z^2 + x^2)\hat{p}_y^2 + (x^2 + y^2)\hat{p}_z^2 - (yz\hat{p}_y\hat{p}_z - i\hbar y\hat{p}_z) - (yz\hat{p}_z\hat{p}_y - i\hbar z\hat{p}_y) - (xz\hat{p}_x\hat{p}_z - i\hbar x\hat{p}_z) - (xz\hat{p}_z\hat{p}_x - i\hbar z\hat{p}_x) - (xy\hat{p}_x\hat{p}_y - i\hbar x\hat{p}_y) - (xy\hat{p}_y\hat{p}_x - i\hbar y\hat{p}_x)$

**对易式恒等式：**

$$[\hat{A}, \hat{B}\hat{C}] = \hat{A}\hat{B}\hat{C} - \hat{B}\hat{C}\hat{A} = \hat{A}(\hat{B}\hat{C} - \hat{C}\hat{B}) + \hat{A}\hat{C}\hat{B} - \hat{B}\hat{C}\hat{A} = \hat{A}[\hat{B}, \hat{C}] + [\hat{A}, \hat{C}]\hat{B}$$

$\hat{B}$ 左移变边缘，可提公因式。

$$[\hat{A}\hat{B}, \hat{C}] = \hat{A}\hat{B}\hat{C} - \hat{C}\hat{A}\hat{B} = \hat{A}(\hat{B}\hat{C} - \hat{C}\hat{B}) + \hat{A}\hat{C}\hat{B} - \hat{C}\hat{A}\hat{B} = \hat{A}[\hat{B}, \hat{C}] + [\hat{A}, \hat{C}]\hat{B}$$

$$[\hat{A}, \hat{B}\hat{C}] = [\hat{A}, \hat{B}]\hat{C} + \hat{B}[\hat{A}, \hat{C}], \quad [\hat{A}\hat{B}, \hat{C}] = \hat{A}[\hat{B}, \hat{C}] + [\hat{A}, \hat{C}]\hat{B}$$

$[\hat{L}^2, \hat{L}_x] = [\hat{L}_y^2, \hat{L}_x] + [\hat{L}_z^2, \hat{L}_x] = \hat{L}_y[\hat{L}_y, \hat{L}_x] + [\hat{L}_y, \hat{L}_x]\hat{L}_y + \hat{L}_z[\hat{L}_z, \hat{L}_x] + [\hat{L}_z, \hat{L}_x]\hat{L}_z = \hat{L}_y(-i\hbar\hat{L}_z) + (-i\hbar\hat{L}_z)\hat{L}_y + \hat{L}_z(i\hbar\hat{L}_y) + (i\hbar\hat{L}_y)\hat{L}_z = 0$

同理 $[\hat{L}^2, \hat{L}_y] = [\hat{L}^2, \hat{L}_z] = 0$。

JNTVERSITYOF SCIENCEANDTE
要求是到脚
③角动量的对易式

μ空间的分布
ERSITY OF SCIENCE AND TE
△M的分割举例

-（或段﹣发）-(xy院罚﹣院）-(yx院段﹣yP高）

化中过星刷厂
OHZWH◇中科技大。