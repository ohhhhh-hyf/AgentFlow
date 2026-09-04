# 简单塞曼效应

无外加电磁场时，$A_0 = P + V(r)$，$V(r) = -kF - \lambda K$

加入磁场 $\mathbf{B} = B\mathbf{e}_z$，$A' = \frac{1}{2}B \times r$，$A = A_0 + A'$（后证）

电荷为 $q$，质量为 $m$ 的粒子在矢势 $A$ 和标势 $\phi$ 中，有 $H = \frac{1}{2m}|P - qA|^2 + V + q\phi$

对塞曼效应，$\phi = 0$，$V(r) = -\frac{k}{r} - \frac{\lambda}{r^2}$，磁场 $\mathbf{B} = \nabla \times A = B\mathbf{e}_z$，$q = -e$，$R = 0$ 满足库仑规范

选 $A = \frac{1}{2}(-By, Bx, 0)$，则 $H = \frac{1}{2m}\left[(p_x + \frac{eB}{2}y)^2 + (p_y - \frac{eB}{2}x)^2 + p_z^2\right] + V(r)$

$H = \frac{p^2}{2m} + \frac{eB}{2m}(xp_y - yp_x) + \frac{e^2B^2}{8m}(x^2 + y^2) + V(r)$，令 $\omega_L = \frac{eB}{2m}$，$\rho^2 = x^2 + y^2$，又 $L_z = xp_y - yp_x$

则 $H = \frac{p^2}{2m} + \omega_L L_z + V(r)$，$\omega_L^2 \rho^2 \ll \omega_L$，可忽略 $\Rightarrow H = \frac{p^2}{2m} + \omega_L L_z + V(r) = H_0 + H'$

$H\psi_{nlm} = E_{nlm}\psi_{nlm}(r, \theta, \phi) = R_{nl}(r)Y_{lm}(\theta, \phi)$

则 $-\frac{\hbar^2}{2m}\left[\frac{1}{r^2}\frac{\partial}{\partial r}\left(r^2\frac{\partial}{\partial r}\right) + \frac{1}{r^2\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial}{\partial\theta}\right) + \frac{1}{r^2\sin^2\theta}\frac{\partial^2}{\partial\phi^2}\right]R(r)Y(\theta,\phi) + V(r)R(r)Y + \omega_L m\hbar R(r)Y = E R(r)Y$

于是有 $\left[-\frac{\hbar^2}{2m}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right) + \frac{\hbar^2 l(l+1)}{2mr^2} + V(r)\right]R(r)Y(\theta,\phi) = (E - \omega_L m\hbar)R(r)Y(\theta,\phi)$ ②

**注意**：左式 $= \left[-\frac{\hbar^2}{2m}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right) - \frac{\hbar^2}{2mr^2}\left(\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2}{\partial\phi^2}\right) + V(r) - \omega_L m\hbar\right]R(r)Y(\theta,\phi) = ER(r)Y(\theta,\phi)$

$-\frac{\hbar^2}{2m}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right)Y(\theta,\phi) - \frac{\hbar^2}{2mr^2}R(r)\left[\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial Y}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2 Y}{\partial\phi^2}\right] + V(r)R(r)Y(\theta,\phi) - \omega_L m\hbar R(r)Y - ER(r)Y(\theta,\phi) = 0$

$\Rightarrow -\frac{\hbar^2}{2m}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + V(r) - E = \frac{\hbar^2}{2mr^2}\left[\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial Y}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2 Y}{\partial\phi^2}\right] \cdot \frac{1}{Y}$ (?)

令 $E_0 = E - \omega_L m\hbar = E - \frac{eB}{2m}m\hbar$，代入 $V(r) = -\frac{k}{r} - \frac{\lambda}{r^2}$

则 $-\frac{\hbar^2}{2m}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) - \frac{\lambda}{r^2}R - \frac{k}{r}R - \frac{\hbar^2}{2mr^2}l(l+1)R - (\omega_L m\hbar - E) = 0$

$\frac{d^2R}{dr^2} + \frac{2}{r}\frac{dR}{dr} + \frac{2m}{\hbar^2}\left(E_0 + \frac{k}{r} - \frac{\lambda}{r^2} - \frac{\hbar^2 l(l+1)}{2mr^2}\right)R(r) = 0$，对比碱金属原子方程，有 $E_0 = -\frac{k^2m}{2\hbar^2} \cdot \frac{1}{n'^2} = -\frac{Ry}{n'^2} \cdot \hbar c$

$n = n_r + l' + 1$，$l'(l'+1) = l(l+1) - 2\lambda$，$E = E_0 + \omega_L m\hbar = E_{nlm} = -\frac{Ry}{n'^2} \cdot \hbar c + m\hbar\omega_L$

**B = 0 时**，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。

**B ≠ 0 时**，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，**不简并**。

# 气体的基本统计规律

## 气体的微观模型

PV = VRT = RT = /ART

P = 器T = y·&T = nkT，n 为单位体积内的粒子数。

标准状态下的气体分子数密度 n₀ = 221，表示每 m² 理想气体中的微观粒子数。

分子线度为 d，则 d³·P·NA = M·d = "《"厌，即可不计分子本身的大小。

**理想气体的微观模型**：
① 可不计分子本身的大小
② 除碰撞外，气体分子间及气体分子同器壁间的相互作用可忽略
③ 分子在两次碰撞间做匀速直线运动

**压强的微观模型**：
① 宏观上认为器壁受连续作用力
② 热平衡时，假设分子和器壁的碰撞是弹性碰撞
③ 分子混沌性假设：平衡态时，气体分子的热运动速度无择优方向

第 i 个分子与 A 碰撞，y、z 分量不变，x 方向速度分量由 Vₓᵢ → -Vₓᵢ。

第 i 个分子单位时间与 A 碰撞次数为（器），单位时间单位面积冲量即压强。

P = (2mvₓ/bc) = p = +pᵢ =

= = ＝言，则 p = 3/4 mv² = 3nmr

Eₖ = ±mP 为粒子的平均动能。p = 1/3 nε = nkT => ε = 3/2 KT

## 分子的平均动能与理想气体系统的内能

只考虑分子平动动能，U = 萬Eᵢ = NE = 3/2 KNT = 3/2 URT

定体热容 Cᵥ = (∂U/∂T)ᵥ = 3/2 WR，Cᵥ,ₘ = 3/2 R。

化中付应明一

## 近独立粒子系的麦克斯韦-玻尔兹曼分布能量分布律

### 微观粒子基本运动状态的经典描述（能量、坐标、动量）

#### ① 自由平动粒子

在三维空间中运动时，粒子的自由度为 3，位置由 $x, y, z$ 标定，与之共轭的动量为 $P_x = m\dot{x}, P_y = m\dot{y}, P_z = m\dot{z}$，$\dot{x}$ 表示 $x$ 对时间的导数。

无外力作用时，$E = \frac{1}{2m}(P_x^2 + P_y^2 + P_z^2)$。粒子状态可由 $x, y, z, P_x, P_y, P_z$ 确定。

#### ② 线性谐振子

质量为 $m$ 的粒子在弹性力 $F = -Ax$ 作用下在平衡点附近作简谐运动，振动圆频率 $\omega = \sqrt{\frac{A}{m}}$。

$$E = \frac{P^2}{2m} + \frac{1}{2}Ax^2 = \frac{P^2}{2m} + \frac{1}{2}m\omega^2 x^2$$

以 $x, p$ 为直角坐标可构成二维 $\mu$ 空间，若 $E$ 给定，则代表点的轨迹是椭圆，椭圆面积 $= \frac{\pi}{\omega} \cdot \frac{2E}{m} \cdot \sqrt{\frac{m}{2E}} = \frac{\pi E}{\omega}$，即 $S = \frac{E}{\nu}$（其中 $\nu = \frac{\omega}{2\pi}$）。

#### ③ 转子（双原子分子整体刚性转动）

- ONG UNIVERSITY OF SCIENCE AND TECHNOLOGY

考虑质量为 $m$ 的质点 A 被具有一定长度的轻杆系于原点时所做运动（$r$ 一定）：

$$E = \frac{1}{2}m(\dot{x}^2 + \dot{y}^2 + \dot{z}^2), \quad x = r\sin\theta\cos\varphi, \quad y = r\sin\theta\sin\varphi, \quad z = r\cos\theta$$

$$E = \frac{1}{2}m(\dot{r}^2 + r^2\dot{\theta}^2 + r^2\sin^2\theta\dot{\varphi}^2) = \frac{1}{2}m(r^2\dot{\theta}^2 + r^2\sin^2\theta\dot{\varphi}^2)$$

对于双原子分子，两质点系统绕质心转动可约化为质量为 $\mu$ 的单体转动问题。$\mu = \frac{m_1 m_2}{m_1 + m_2}$。取质心为坐标原点，$m_1$ 原子距原点 $r_1$，$m_2$ 原子距原点 $r_2$：

$$r_1 = \frac{m_2}{m_1 + m_2}r, \quad r_2 = \frac{m_1}{m_1 + m_2}r$$

$$I_{总} = m_1 r_1^2 + m_2 r_2^2 = \mu r^2$$

系统转动能量：

$$T_{转} = \frac{1}{2}m_1 r_1^2(\dot{\theta}^2 + \sin^2\theta\dot{\varphi}^2) + \frac{1}{2}m_2 r_2^2(\dot{\theta}^2 + \sin^2\theta\dot{\varphi}^2)$$

即：

$$T_{转} = \frac{1}{2}\mu r^2(\dot{\theta}^2 + \sin^2\theta\dot{\varphi}^2) = \frac{1}{2}I(\dot{\theta}^2 + \sin^2\theta\dot{\varphi}^2) = \frac{P_\theta^2}{2I} + \frac{P_\varphi^2}{2I\sin^2\theta}$$

$$P_\theta = \mu r^2\dot{\theta} = P_{\theta 1} + P_{\theta 2}, \quad P_\varphi = \mu r^2\sin^2\theta\dot{\varphi} \quad (\text{与 } \theta, \varphi \text{ 共轭的动量})$$

$$T_{总} = \frac{1}{2}\mu r^2\dot{\theta}^2 + \frac{1}{2}\mu r^2\sin^2\theta\dot{\varphi}^2 = \frac{1}{2I}\left(P_\theta^2 + \frac{P_\varphi^2}{\sin^2\theta}\right)$$

## 宏观分布、组、态、微观态

### M空间分割（宏观）

把 $\mu$ 空间分成许多小体元 $\Delta \omega_j (j=1,2,\dots,l)$，大小适当，足够小到可近似认为代表点落在 $\Delta \omega_j$ 内的粒子运动状态相同，但也不是无穷小，要满足 $\Delta \omega_j \geq 10$（统计需要）。

### 宏观分布与宏观态（与M空间的分布 $\{a_j\}$ 对应）

宏观状态参量是相应微观物理量的统计平均值。

知道了 $\Delta \omega_j (j=1,2,\dots,l)$ 体元内代表点的数目 $a_j (j=1,2,\dots,l)$，即可确定系统的内能等宏观量的平均值，从而系统的宏观态也就确定了。

### 宏观分布的组态（配容）（哪些粒子的代表点在 $\Delta \omega_i$ 内）

经典力学中，粒子是可分辨的，交换两粒子的状态会改变系统的状态（微观）。

一个宏观分布 $\{a_j\}$ 对应的组态数 $W = \dfrac{N!}{\prod_j a_j!}$，即将 $N$ 个粒子按 $\{a_j\}$ 分布给 $l$ 个状态的可能数。

### 经典力学中一个组态的微观数（相字 $\Delta \omega_j \to$ 相格 $h_0^r$，过渡到微观）

粒子的状态是连续的，粒子和系统的微观运动状态不可数 $\Rightarrow$ 人为划出最小的"格子"。

将 $p_i, q_i$ 分为等间隔区域，$\delta p_i \delta q_i = h_0 \Rightarrow (\delta q_1 \delta p_1)\dots(\delta q_r \delta p_r) = h_0^r$，相格 $h_0^r$ 代表一个粒子态。

子相字空间小体元 $\Delta \omega_j (j=1,2,\dots,l)$ 中粒子运动状态数为 $\Delta \omega_j = \dfrac{\Delta \omega_j}{h_0^r}$，$a_j$ 个粒子在 $\Delta \omega_j$ 个运动状态上分布的可能微观状态数为 $\binom{a_j + \Delta \omega_j - 1}{a_j}$，多个粒子可以处于同一相格内。

### 一个分布的微观分布数

$$W = \prod_j \binom{a_j + \Delta \omega_j - 1}{a_j} = \prod_j \frac{(a_j + \Delta \omega_j - 1)!}{a_j! (\Delta \omega_j - 1)!}$$

## 等概率原理和最概然统计

若系统的各微观态无更多限制，就假定一切符合所有约束条件的微观态出现的概率相等。

**最概然统计**：认为出现概率最大（即微观态数最多）的那个宏观态分布对应于系统的平衡态。

## 最概然分布求算

一个宏观态分布 $\{a_j\}$ 出现的微观态数为 $\Omega$，则 $\Omega$ 最大也即 $\ln\Omega$ 最大，$\delta(\ln\Omega)=0$（即 $d(\ln\Omega)=0$）。

$$\Omega = \frac{N!}{\prod_j a_j!} \prod_j (\omega_j)^{a_j}, \quad \ln\Omega = \ln N! - \sum_j \ln a_j! + \sum_j a_j \ln(\omega_j)$$

$$\delta(\ln\Omega) = \delta(\ln N!) - \sum_j \delta(\ln a_j!) + \sum_j \ln(\omega_j) \cdot \delta a_j = \sum_j [\ln(\omega_j) - \ln a_j!] \delta a_j = 0$$

由斯特林公式，$N$ 足够大时，有 $\ln N! \approx N\ln N - N$。

则 $\sum_j (\ln a_j + 1 - 1) \delta a_j - \sum_j \ln(\omega_j) \delta a_j = \sum_j (\ln a_j - \ln \omega_j) \delta a_j = 0$。

又有粒子数和能量守恒条件（孤立系），则 $\sum_j \delta a_j = 0$，$\sum_j \varepsilon_j \delta a_j = 0$。

令 $f(a_1, a_2, \dots, a_c, \alpha, \beta) = \sum_j a_j (\ln a_j - 1) - \sum_j \ln(\omega_j) a_j + \alpha (\sum_j a_j - N) + \beta (\sum_j \varepsilon_j a_j - E)$

则 $f$ 取极值时，$\frac{\partial f}{\partial a_j} = 0$，$\frac{\partial f}{\partial \alpha} = \frac{\partial f}{\partial \beta} = 0$。$\ln a_j + \alpha + \beta \varepsilon_j = 0$。

> $a_j = \omega_j e^{-\alpha - \beta \varepsilon_j}$，且此时 $f$ 取极大值。

$\beta = \frac{1}{kT}$，是一个普遍量，$a_j = \omega_j e^{-\alpha - \beta \varepsilon_j}$。

由 $\sum_j a_j = N$，则 $e^{-\alpha} \sum_j \omega_j e^{-\beta \varepsilon_j} = N$。引入配分函数 $Z = \sum_j \omega_j e^{-\beta \varepsilon_j}$，则 $e^{-\alpha} = \frac{N}{Z}$。

## MB分布的物理意义

**MB分布是出现概率最大的一种分布**，别的分布出现的概率可忽略，**MB分布给出了系统处于平衡态时同一时刻系统内粒子取某一能量值的概率**。

宏观态

- △M；可继续细分
- 一种分布有多种实现方法
- 多个组态
- 一个组态有多种微观态
- μ空间的分布

fasf

## MB分布的物理意义

### △M的分割举例

二维线性谐振子 $\varepsilon = \frac{1}{2m}(p_x^2 + p_y^2) + \frac{1}{2}m\omega^2(x^2 + y^2)$，代表点的轨迹为椭圆（$\mu$ 空间）。

$S = \oint p\,dq = \Delta M$

$\varepsilon = \mu$ 时，$\Delta M = h$。

偏离最概然分布的概率很小，平衡态对应的微观态数为 $W^*$，最概然分布附近一个分布对应的微观态数为 $W$。假设 $N = 2n$ 个粒子处在一个体积 $V$ 的空间中，将 $V$ 等体积划分为 $\Delta M$ 份。

$W^* = \frac{N!}{\prod n_i!}$，$W = \frac{N!}{\prod (n_i \pm \Delta n_i)!}$，$\ln\left(\frac{W}{W^*}\right) = -\sum \frac{\Delta n_i^2}{2n_i}$，$n$ 很大，$\frac{\Delta n}{n} \to 0$。

### 量子态中的 $\mu$ 空间

$\Delta X \Delta P_x \gtrsim h$，一个粒子的代表不再是点，而是一团“小空间”。粒子的状态是分立的，不再需要用“$\mu$ 空间”，只需考虑分立能级上的分布即可。

三维平动子能级 $\varepsilon_{n_x,n_y,n_z} = \frac{h^2}{8mV^{2/3}}(n_x^2 + n_y^2 + n_z^2)$

刚性转子能级 $\varepsilon = \frac{l(l+1)\hbar^2}{2I}$，$[2l+1 = (l+1)^2 - l^2]$

谐振子能级 $\varepsilon = \left(n + \frac{1}{2}\right)\hbar\omega$

平动子能级间隔极小，可视为连续分布，按 $\mu$ 空间能级；常温下，转动也可看作连续（不含 $H_2$）；振动一般必须看作分立能级，直接分析量子能级简并度。

### 量子态与相空间体积之间的对应关系

对于一个自由度为 $r$ 的粒子，它的 $\mu$ 空间中大小为 $h^r$ 的相体积对应一个量子态。

三维平动子：$0 \sim \varepsilon$ 范围内的总量子态数 $\Omega(\varepsilon) = \frac{4\pi}{3}\frac{(2m\varepsilon)^{3/2}}{h^3}V = \frac{V}{h^3}\cdot\frac{4\pi}{3}(2m\varepsilon)^{3/2}$

双原子分子刚性转子：$\mathrm{d}\tau = \mathrm{d}\varphi \, \mathrm{d}p_\varphi \, \mathrm{d}\theta \, \mathrm{d}p_\theta$，$\varepsilon = \frac{1}{2I}\left(p_\theta^2 + \frac{p_\varphi^2}{\sin^2\theta}\right)$

$p_\theta = \sqrt{2I\varepsilon}\cos\theta$，$p_\varphi = \sqrt{2I\varepsilon}\sin\theta\sin\varphi$，$\mathrm{d}p_\theta \mathrm{d}p_\varphi = \begin{vmatrix} -\sqrt{2I\varepsilon}\sin\theta & 0 \\ \sqrt{2I\varepsilon}\cos\theta\cos\varphi & \sqrt{2I\varepsilon}\sin\theta\cos\varphi \end{vmatrix} \mathrm{d}\theta \mathrm{d}\varphi = I\varepsilon \sin\theta \cos\theta \, \mathrm{d}\theta \, \mathrm{d}\varphi$

$\Omega(\varepsilon) = \frac{1}{h^2}\int_0^{2\pi}\mathrm{d}\varphi \int_0^{\pi} I\varepsilon \sin\theta\cos\theta \, \mathrm{d}\theta = \frac{8\pi^2 I\varepsilon}{h^2}$（四维：$\theta$、$\varphi$、$p_\theta$、$p_\varphi$，$0 < \theta < \pi$，$0 < \varphi < 2\pi$）

# 华中科技大学

## 算符

### 狄拉克符号

- $|4\rangle$：右矢；$\langle 4|$：左矢，称 $|4\rangle$ 或 $\langle 4|$ 为态矢，$4$ 是一个标签，用于区分不同的量子态
- $\langle 4| = (|4\rangle)^\dagger$，左矢与右矢是一种共轭转置关系。$\langle a\psi| = a^*\langle \psi|$（$a$ 为复数）
- 内积：$(\varphi, \psi) = \langle \varphi|\psi\rangle$，坐标表象 $\langle \varphi|\psi\rangle = \int \varphi^*(\mathbf{r}) \psi(\mathbf{r}) \, d\tau$，$d\tau = dxdydz$ 为微体积元，$\psi(\mathbf{r}) = \psi(x,y,z)$
- $\langle \varphi|\psi\rangle^* = \langle \psi|\varphi\rangle$，用定积分理解是共轭，用矩阵理解是转置后取共轭
- **正交**：$\langle \varphi|\psi\rangle = 0$ 代表 $\varphi$ 和 $\psi$ 是正交的；**归一**：$\langle \psi|\psi\rangle = 1$ 代表 $\psi$ 是归一化的
- **平均值**：力学量 $A$ 在归一化量子态 $\psi$ 下的平均值 $\bar{A} = \langle \psi|A|\psi\rangle$
- $|\psi\rangle$ 与 $\langle \psi|$ 是量子态 $\psi$ 在右矢、左矢空间的不同表示

### 左、右矢空间的算符运算

设 $A$ 和 $\tilde{A}$ 是两个算符，$\forall |\varphi\rangle$ 和 $|\psi\rangle$，若 $\langle \varphi|A|\psi\rangle = \langle \psi|\tilde{A}|\varphi\rangle^*$，则称 $\tilde{A}$ 为 $A$ 的转置算符。

- $A|\psi\rangle = |A\psi\rangle$，在右矢空间中，$|\psi'\rangle = A|\psi\rangle = |A\psi\rangle$，默认 $A$ 向右作用；在左矢空间中，$\langle \psi'| = \langle \psi|A^\dagger$，算符 $A^\dagger$（$A^\dagger$）向左作用
- $\langle \psi|A^T = \langle A\psi| = \langle \psi|A$。若 $A$ 为厄米算符，则 $\langle \psi'| = \langle \psi|A$
- **→ 厄米算符在左、右矢空间中的运算具有形式不变性**
- 算符在左矢和右矢之间的转换本质上是对偶空间的伴随映射
- 关于 $(A|\psi\rangle)^\dagger = \langle \psi|A^\dagger$：$A = \langle \varphi|A|\psi\rangle$，$A^\dagger = \langle \psi|A^\dagger|\varphi\rangle$，$A^* = \langle \psi|A|\varphi\rangle^* = \langle \varphi|A^\dagger|\psi\rangle \Rightarrow \langle A\varphi| = \langle \varphi|A^\dagger$
- $\langle \psi|AB|\varphi\rangle = \langle \psi|AB|\varphi\rangle$（先将 $B|\varphi\rangle$ 视为一体，再作变换）

### 基矢与本征方程

基矢与本征方程

设算符 $\hat{F}$ 作用于态矢 $| \psi \rangle$ 上，若满足  
$\hat{F} | \psi \rangle = \lambda | \psi \rangle$，则称 $| \psi \rangle$ 为算符 $\hat{F}$ 的本征态，$\lambda$ 为本征值。

- $F|\psi\rangle = \lambda|\psi\rangle$，称 $|\psi\rangle$ 为算符 $F$ 的本征态，$\lambda$ 为本征值
- **能量本征方程**：$H|k\rangle = E_k|k\rangle$，将 $|k\rangle$ 简记为 $|k\rangle$（为基矢），量子数 $k$ 标记系统所有量子数

## ③ 角动量的对易式

角动量分量表达式：

$$L_x = yP_z - zP_y, \quad L_y = zP_x - xP_z, \quad L_z = xP_y - yP_x$$

**角动量与坐标的对易关系：**

$$[L_x, x] = [yP_z - zP_y, x] = 0 \quad \Rightarrow \quad [L_\alpha, x] = 0 \quad (\alpha = x, y, z)$$

$$[L_x, y] = [yP_z, y] - [zP_y, y] = -[zP_y, y] = i\hbar z$$

$$[L_x, z] = [yP_z - zP_y, z] = [yP_z, z] = -i\hbar y \quad (\text{或 } [L_x, z] = -i\hbar y)$$

同理有：

$$[L_y, x] = -i\hbar z, \quad [L_y, z] = i\hbar x, \quad [L_z, x] = i\hbar y, \quad [L_z, y] = -i\hbar x$$

**角动量与动量的对易关系：**

$$[L_x, P_x] = [yP_z - zP_y, P_x] = 0 \quad \Rightarrow \quad [L_\alpha, P_\alpha] = 0 \quad (\alpha = x, y, z)$$

$$[L_x, P_y] = [yP_z - zP_y, P_y] = [yP_z, P_y] = y(-i\hbar \partial_x) = i\hbar P_z$$

$$[L_x, P_z] = [yP_z - zP_y, P_z] = -[zP_y, P_z] = -i\hbar P_y$$

同理有：

$$[L_y, P_x] = -i\hbar P_z, \quad [L_y, P_z] = i\hbar P_x, \quad [L_z, P_x] = i\hbar P_y, \quad [L_z, P_y] = -i\hbar P_x$$

**角动量各分量之间的对易关系：**

$$[L_x, L_x] = 0 \quad \Rightarrow \quad [L_\alpha, L_\alpha] = 0 \quad (\alpha = x, y, z)$$

$$[L_x, L_y] = [yP_z - zP_y, zP_x - xP_z] = [yP_z, zP_x] - [yP_z, xP_z] - [zP_y, zP_x] + [zP_y, xP_z]$$

$$= [yP_z, zP_x] + [zP_y, xP_z] = y[P_z, z]P_x + x[z, P_z]P_y = y(-i\hbar)P_x + x(i\hbar)P_y = i\hbar L_z$$

同理：

$$[L_y, L_z] = i\hbar L_x, \quad [L_z, L_x] = i\hbar L_y$$

**对易式恒等式：**

$$[A, BC] = ABC - BCA = A(BC - CB) + ACB - BCA = A[B, C] + [A, C]B$$

> B 左移变边缘，可提公因式。

$$[AB, C] = (AB)C - C(AB) = ABC - ACB + ACB - CAB = [A, C]B + A[B, C]$$

即：

$$[A, BC] = [A, B]C + B[A, C]$$

$$[AB, C] = A[B, C] + [A, C]B$$

**角动量平方算符：**

令 $L^2 = L_x^2 + L_y^2 + L_z^2$，则：

$$L^2 = (yP_z - zP_y)^2 + (zP_x - xP_z)^2 + (xP_y - yP_x)^2$$

展开得：

$$L^2 = (y^2 + z^2)P_x^2 + (z^2 + x^2)P_y^2 + (x^2 + y^2)P_z^2 - (yzP_yP_z - i\hbar yP_z) - (yzP_zP_y - i\hbar zP_y) - (xzP_xP_z - i\hbar xP_z) - (xzP_zP_x - i\hbar zP_x) - (xyP_xP_y - i\hbar xP_y) - (xyP_yP_x - i\hbar yP_x)$$

**角动量平方与分量的对易：**

$$[L^2, L_z] = [L_x^2 + L_y^2, L_z] = L_x[L_x, L_z] + [L_x, L_z]L_x + L_y[L_y, L_z] + [L_y, L_z]L_y$$

$$= L_x(-i\hbar L_y) + (-i\hbar L_y)L_x + L_y(i\hbar L_x) + (i\hbar L_x)L_y = 0$$

同理 $[L^2, L_x] = [L^2, L_y] = 0$。

F14>＝入14)，称（4＞为算符户的本征态，入为本征值．
JNTVERSITYOF SCIENCEANDTE
要求是到脚

-（或段﹣发）-(xy院罚﹣院）-(yx院段﹣yP高）

UNIVERSITY OF SCIENCB AND TE

ERSITY OF SCIENCE AND TE

OHZWH◇中科技大。