# 一维束缚态

在一维情况下，Aψ=Eψ简化为：

$$\left[-\frac{\hbar^2}{2\mu}\frac{d^2}{dx^2}+V(x)\right]\psi(x)=E\psi(x)$$

## 定理1（势函数不连续时）

设 $V(x)=V_1$（$x<a$），$V(x)=V_2$（$x>a$），在 $x=a$ 处不连续，有一个跳跃。当 $V_1-V_2$ 有限时，能量本征函数 $\psi(x)$ 及其导函数 $\psi'(x)=\frac{d\psi}{dx}$ 在 $a$ 点是连续的。

$\psi(x)$ 本身连续是因为概率幅的连续性问题（$\psi(x)$ 是概率波！）。

**证明思路：**

- 思路1：$|\psi(x)|<E$，当 $E\to 0$ 时右式 $\to 0$
- 思路2：反证法，若 $\psi(x)$ 不连续，则 $\psi(x)$ 含冲击项，不符合薛定谔方程
- 思路3：连续性方程 $\frac{\partial P(x,t)}{\partial t}+\frac{\partial j(x,t)}{\partial x}=0$，其中 $\rho=\psi^*\psi=|\psi|^2$，$j=-\frac{i\hbar}{2\mu}(\psi^*\nabla\psi-\psi\nabla\psi^*)$，连续 $\Rightarrow \psi,\psi'$ 连续

## 一维半无限深方势阱

$$V(x)=\begin{cases} \infty, & x<0 \\ 0, & 0<x<a \\ V_0, & x>a \end{cases}$$

定态薛定谔方程：

$$-\frac{\hbar^2}{2\mu}\frac{d^2\psi}{dx^2}+V(x)\psi(x)=E\psi(x)$$

**分区求解：**

- $x<0$ 区域：$\because V(x)=\infty$，物理上不允许粒子在此区域出现，故有 $\psi(x)=0$（$x<0$）
- 由 $\psi(0)=0$，则 $\psi(x)=A\sin kx$
- $x>a$ 区域：有 $\psi''(x)-\frac{2\mu}{\hbar^2}(V_0-E)\psi(x)=0$。令 $\beta=\frac{\sqrt{2\mu(V_0-E)}}{\hbar}$，则 $\psi(x)=Be^{\beta x}+Ce^{-\beta x}$

$\because \psi(x)\xrightarrow{x\to\infty}0$，若 $\beta$ 为虚数即 $V_0<E$，$\psi(x)$ 周期振荡不满足束缚态，故仅考虑 $\beta$ 为实数且 $>0$。

当 $x\to\infty$ 时 $e^{\beta x}\to\infty$，$\therefore C=0$，$\psi(x)=Be^{-\beta x}$。

由边界条件：
$$\psi(a)=Be^{-\beta a}=A\sin ka$$
$$\psi'(a)=-\beta Be^{-\beta a}=kA\cos ka$$

于是有：
$$k\cot ka=-\beta=-\frac{\sqrt{2\mu(V_0-E)}}{\hbar}$$

且 $\cot ka<0$。能量满足超越方程：
$$E=\frac{\hbar^2}{2\mu a^2}\left[1-\cos(2ka)\right]$$

且 $\cot(ka)<0$，能量是量子化的。

---

# 理想气体微观模型

标准状态下的气体分子数密度 $n_0=\frac{p_0}{kT_0}$，表示每 $\text{m}^3$ 理想气体中的微观粒子数。

分子线度为 $d$，则 $d \ll \bar{l}$（平均自由程），即可不计分子本身的大小。

## 理想气体的微观模型

1. 可不计分子本身的大小
2. 除碰撞外，气体分子间及气体分子同器壁间的相互作用可忽略
3. 分子在两次碰撞间做匀速直线运动

## 压强的微观模型

1. 宏观上认为器壁受连续作用力
2. 热平衡时，假设分子和器壁的碰撞是弹性碰撞
3. 分子混沌性假设：平衡态时，气体分子的热运动速度无择优方向

设第 $i$ 个分子与 $A_1$ 面碰撞，$y,z$ 分量不变，$x$ 方向速度分量由 $v_{ix}$ 变为 $-v_{ix}$。

$$P=\frac{2mv_{ix}}{\Delta t \cdot bc}=\frac{1}{3}nm\overline{v^2}$$

其中 $\overline{v^2}=\frac{3kT}{m}$，$n$ 为分子数密度。

$$\therefore P=nkT$$

$E_t=\frac{1}{2}m\overline{v^2}$ 为粒子的平均平动动能。

$$\therefore P=\frac{2}{3}nE_t=nkT \Rightarrow E_t=\frac{3}{2}kT$$

## 分子的平均动能与理想气体系统的内能

只考虑分子平动动能：
$$U=N E_t=\frac{3}{2}NkT=\frac{3}{2}RT$$

定体热容：
$$C_V=\left(\frac{\partial U}{\partial T}\right)_V=\frac{3}{2}R,\quad C_{V,m}=\frac{3}{2}R$$

---

# 近独立粒子系的麦克斯韦—玻尔兹曼分布能量分布律

## 微观粒子基本运动状态的经典描述（能量、坐标、动量）

### 自由平动粒子

在三维空间中运动时，粒子的自由度为3，位置由 $x,y,z$ 标定，与之共轭的动量为 $P_x=m\dot{x}$，$P_y=m\dot{y}$，$P_z=m\dot{z}$（$\dot{x}$ 表示 $x$ 对时间的导数）。

无外力作用时：
$$E=\frac{1}{2m}(P_x^2+P_y^2+P_z^2)$$

粒子状态可由 $x,y,z,P_x,P_y,P_z$ 确定。

### 线性谐振子

质量为 $m$ 的粒子在弹性力 $F=-kx$ 作用下在平衡点附近作简谐运动，振动圆频率 $\omega=\sqrt{\frac{k}{m}}$。

$$E=\frac{P^2}{2m}+\frac{1}{2}m\omega^2 x^2 \Rightarrow \frac{P^2}{2m\varepsilon}+\frac{m\omega^2 x^2}{2\varepsilon}=1$$

以 $x,P$ 为直角坐标可构成二维 $\mu$ 空间，若 $\varepsilon$ 给定，则代表点的轨迹是椭圆，椭圆面积 $=\pi\sqrt{\frac{2\varepsilon}{m}}\cdot\sqrt{\frac{2\varepsilon}{m\omega^2}}=\frac{2\pi\varepsilon}{\omega}$。

即 $S=\frac{2\pi\varepsilon}{\omega}$。

### 转子（双原子分子整体刚性转动）

考虑质量为 $m$ 的质点 $A$ 被具有一定长度的轻杆系于原点时所做运动（$r$ 一定）：

$$E=\frac{1}{2}m(\dot{x}^2+\dot{y}^2+\dot{z}^2)$$

其中 $x=r\sin\theta\cos\varphi$，$y=r\sin\theta\sin\varphi$，$z=r\cos\theta$。

$$E=\frac{1}{2}m(r^2\dot{\theta}^2+r^2\sin^2\theta\dot{\varphi}^2)$$

对于双原子分子，两质点绕系统质心转动可约化为质量 $\mu$ 的单体转动问题。

系统转动能量：
$$T=\frac{1}{2}m_1r_1^2(\dot{\theta}^2+\sin^2\theta\dot{\varphi}^2)+\frac{1}{2}m_2r_2^2(\dot{\theta}^2+\sin^2\theta\dot{\varphi}^2)$$

即：
$$T=\frac{1}{2}\mu r_e^2(\dot{\theta}^2+\sin^2\theta\dot{\varphi}^2)$$

与 $\theta,\varphi$ 共轭的动量：
$$P_\theta=\mu r_e^2\dot{\theta},\quad P_\varphi=\mu r_e^2\sin^2\theta\dot{\varphi}$$

$$T=\frac{1}{2\mu r_e^2}\left(P_\theta^2+\frac{P_\varphi^2}{\sin^2\theta}\right)$$

---

## 宏观分布、组态、微观态

### μ空间分割（宏观）

把μ空间分成许多小体元 $\Delta\mu_j$（$j=1,2,\cdots,l$），$\Delta\mu_j$ 大小适当，足够小到可近似认为代表点落在 $\Delta\mu_j$ 内的粒子运动状态相同，但也不是无穷小，要满足 $\Delta\mu_j \geq h^3$（统计需要）。

### 宏观分布与宏观态（与μ空间的分布 $\{a_j\}$ 对应）

宏观状态参量是相应微观物理量的统计平均值。

知道了 $\Delta\mu_j$（$j=1,2,\cdots,l$）体元内代表点的数目 $a_j$（$j=1,2,\cdots,l$），即可确定系统的内能等宏观量的平均值，从而系统的宏观态也就确定了。

### 宏观分布的组态（配容）（哪些粒子的代表点在 $\Delta\mu_j$ 内）

经典力学中，粒子是可分辨的，交换两粒子的状态会改变系统的状态（微观）。

一个宏观分布 $\{a_j\}$ 对应的组态数：
$$W=\frac{N!}{\prod_j a_j!}$$

即将 $N$ 个粒子按 $\{a_j\}$ 分布给 $l$ 个状态的可能数。

### 经典力学中一个组态的微观数（相字 $\Delta\mu_j$ → 相格 $h^r$，过渡到微观）

粒子的状态是连续的，粒子和系统的微观运动状态不可数，人为划出最小的格子。

将 $P_i,q_i$ 分为等间隔区域，$\delta P_i\delta q_i=h_0$（$i=1,\cdots,r$），$(\delta q_1\delta P_1)\cdots(\delta q_r\delta P_r)=h_0^r$，相格 $h_0^r$ 代表一个粒子态。

子相字空间小体元 $\Delta\mu_j$（$j=1,2,\cdots,l$）中粒子运动状态数为 $\Delta\omega_j=\frac{\Delta\mu_j}{h_0^r}$，$a_j$ 个粒子在 $\Delta\omega_j$ 个运动状态上分布的可能微观状态数为 $\frac{(\Delta\omega_j)^{a_j}}{a_j!}$，多个粒子可以处于同一相格内。

### 一个分布的微观分布数

$$\Omega=\frac{N!}{\prod_j a_j!}\prod_j\frac{(\Delta\omega_j)^{a_j}}{a_j!}=N!\prod_j\frac{(\Delta\omega_j)^{a_j}}{a_j!}$$

---

## 等概率原理和最概然统计

若系统的各微观态无更多限制，就假定一切符合所有约束条件的微观态出现的概率相等。

**最概然统计**：认为出现概率最大（即微观态数最多）的那个宏观态分布对应于系统的平衡态。

---

## 最概然分布求算

由斯特林公式，$N$ 足够大时，有 $\ln N! \approx N\ln N-N$。

$$\delta(\ln\Omega)=\delta\left(\sum_j a_j\ln\frac{\Delta\omega_j}{a_j}\right)=0$$

即：
$$\sum_j(\ln\Delta\omega_j-\ln a_j)\delta a_j=0$$

又有粒子数和能量守恒条件（孤立系）：
$$\sum_j\delta a_j=0,\quad \sum_j\varepsilon_j\delta a_j=0$$

令：
$$f(a_1,a_2,\cdots,a_l,\alpha,\beta)=\sum_j a_j(\ln\Delta\omega_j-\ln a_j)+\alpha\left(\sum_j a_j-N\right)+\beta\left(\sum_j\varepsilon_j a_j-E\right)$$

则 $f$ 取极值时，$\frac{\partial f}{\partial a_j}=0$，即 $-\ln a_j+\ln\Delta\omega_j+\alpha+\beta\varepsilon_j=0$。

$$a_j=\Delta\omega_j e^{-\alpha-\beta\varepsilon_j}$$

且此时 $f$ 取极大值。

$$\beta=\frac{1}{kT}$$

$kT$ 是一个普遍量。

$$a_j=\Delta\omega_j e^{-\alpha-\beta\varepsilon_j}$$

---

## 宏观态与微观态的关系

- 宏观态 $\Delta\mu_j$ 可继续细分
- 一种分布有多种实现方法（多个组态）
- μ空间的分布 → 一个组态有多种微观态
- $\{a_j\}$ 为宏观分布

### Δμ的分割举例

一维线性谐振子 $E=\frac{P^2}{2m}+\frac{1}{2}m\omega^2x^2$，$\frac{P^2}{2mE}+\frac{m\omega^2x^2}{2E}=1$，代表点的轨迹为椭圆（μ空间）。

$$S=\frac{2\pi E}{\omega}=\Delta\mu$$

当 $\Delta E=h\nu$ 时，$\Delta\mu=h$。

**偏离最概然分布的概率很小**：平衡态对应的微观态数为 $W_m$，最概然分布附近一个分布对应的微观态数为 $W$。假设 $N=2n$ 个粒子处在一个体积 $V$ 的空间中，将 $V$ 等体积划分为 $\Delta\mu_1,\Delta\mu_2$。

$$W=\frac{(2n)!}{(n+\Delta n)!(n-\Delta n)!}$$

当 $n$ 很大时，$\frac{W}{W_m}\to 0$。

---

## 量子态中的μ空间

$$\Delta x\Delta P_x\geq\frac{\hbar}{2}$$

一个粒子的代表不再是点，而是一团"小空间"，粒子的状态是分立的，不再需要用"μ空间"，只需考虑分立能级上的分布即可。

- 刚性转子能级：$E=\frac{\hbar^2}{2I}l(l+1)$，简并度 $g_l=2l+1$
- 谐振子能级：$E=\left(n+\frac{1}{2}\right)\hbar\omega$
- 平动子能级间隔极小，可视为连续分布，按 $\Delta\mu$ 分能级；常温下，转动也可看作连续（不含 $H_2$）；振动一般必须看作分立能级，直接分析量子能级简并度。

### 量子态与相空间体积之间的对应关系

对于一个自由度为 $r$ 的粒子，它的μ空间中大小为 $h^r$ 的相体积对应一个量子态。

第一象限 $0\sim p$ 范围内的总量子态数：
$$\Phi(p)=\frac{1}{h^3}\cdot\frac{4\pi}{3}p^3\cdot V=\frac{4\pi V}{3h^3}(2\mu E)^{3/2}$$

---

# 算符与狄拉克符号

## 狄拉克符号

- $|\psi\rangle$：右矢；$\langle\psi|$：左矢，称 $|\psi\rangle$ 或 $\langle\psi|$ 为态矢，$\psi$ 是一个标签，用于区分不同的量子态
- $\langle\psi|=|\psi\rangle^\dagger$，左矢与右矢是一种共轭转置关系。$\langle\psi|a^*\varphi\rangle=a^*\langle\psi|\varphi\rangle$（$a$ 为复数）

**内积**：$(\psi,\varphi)=\langle\psi|\varphi\rangle$

坐标表象：
$$\langle\psi|\varphi\rangle=\int_{-\infty}^{\infty}\psi^*(r)\varphi(r)d\tau$$

其中 $d\tau=dxdydz$ 为微体积元，$\psi^*(r)=\psi^*(x,y,z)$。

$\langle\psi|\varphi\rangle^*=\langle\varphi|\psi\rangle$，用定积分理解是共轭，用矩阵理解是转置后取共轭。

- **正交**：$\langle\psi|\varphi\rangle=0$ 代表 $\psi$ 和 $\varphi$ 是正交的
- **归一**：$\langle\psi|\psi\rangle=1$ 代表 $\psi$ 是归一化的
- **平均值**：力学量 $A$ 在归一化量子态 $\psi$ 下的平均值 $\bar{A}=\langle\psi|\hat{A}|\psi\rangle$

$|\psi\rangle$、$\langle\psi|$ 是量子态 $\psi$ 在右矢、左矢空间的不同表示。

## 左、右矢空间的算符运算

设 $\hat{A}$ 和 $\hat{A}^T$ 是两个算符，$\forall|\psi\rangle$ 和 $|\varphi\rangle$，若 $\langle\varphi|\hat{A}|\psi\rangle=\langle\psi|\hat{A}^T|\varphi\rangle^*$，则称 $\hat{A}^T$ 为 $\hat{A}$ 的转置算符。

在右矢空间中，$|\psi'\rangle=\hat{A}|\psi\rangle=|\hat{A}\psi\rangle$，默认 $\hat{A}$ 向右作用。在左矢空间中，$\langle\psi'|=\langle\psi|\hat{A}^\dagger$，算符 $\hat{A}^\dagger$（$\hat{A}$ 的厄米共轭）向左作用。

$$\langle\psi'|=\langle\hat{A}^\dagger\psi|=\langle\psi|\hat{A}^\dagger$$

若 $\hat{A}$ 为厄米算符，则 $\langle\psi'|=\langle\psi|\hat{A}$。

**厄米算符在左、右矢空间中的运算具有形式不变性。**

算符在左矢和右矢之间的转换本质上是对偶空间的伴随映射。

关于 $(\langle\psi|\hat{A})|\varphi\rangle=\langle\psi|(\hat{A}|\varphi\rangle)$：

$$\langle\psi|\hat{A}|\varphi\rangle=\langle\psi|\hat{A}\varphi\rangle=\langle\hat{A}^\dagger\psi|\varphi\rangle$$

$$\langle\psi|\hat{A}\hat{B}|\varphi\rangle=\langle\hat{B}^\dagger\psi|\hat{A}^\dagger\varphi\rangle=\langle\hat{A}^\dagger\hat{B}^\dagger\psi|\varphi\rangle$$

即 $(\hat{A}\hat{B})^\dagger=\hat{B}^\dagger\hat{A}^\dagger$（先将 $\hat{B}\varphi$ 视为一体，再作变换）。

## 基矢与本征方程

$$\hat{F}|\psi\rangle=\lambda|\psi\rangle$$

称 $|\psi\rangle$ 为算符 $\hat{F}$ 的本征态，$\lambda$ 为本征值。

**能量本征方程**：
$$\hat{H}|k\rangle=E_k|k\rangle$$

将 $|k\rangle$ 简记为 $|k\rangle$（为基矢），量子数 $k$ 标记系统所有量子数。

---

## 角动量的对易式

角动量算符：
$$\hat{l}_x=\hat{y}\hat{p}_z-\hat{z}\hat{p}_y=-i\hbar\left(y\frac{\partial}{\partial z}-z\frac{\partial}{\partial y}\right)$$

$$\hat{l}_y=\hat{z}\hat{p}_x-\hat{x}\hat{p}_z=-i\hbar\left(z\frac{\partial}{\partial x}-x\frac{\partial}{\partial z}\right)$$

$$\hat{l}_z=\hat{x}\hat{p}_y-\hat{y}\hat{p}_x=-i\hbar\left(x\frac{\partial}{\partial y}-y\frac{\partial}{\partial x}\right)$$

### 基本对易式

$$[\hat{x},\hat{p}_x]=i\hbar,\quad [\hat{y},\hat{p}_y]=i\hbar,\quad [\hat{z},\hat{p}_z]=i\hbar$$

其余坐标与动量对易子为零。

### 角动量与坐标的对易关系

$$[\hat{l}_x,\hat{x}]=[\hat{y}\hat{p}_z-\hat{z}\hat{p}_y,\hat{x}]=0$$

$$[\hat{l}_x,\hat{y}]=[\hat{y}\hat{p}_z,\hat{y}]-[\hat{z}\hat{p}_y,\hat{y}]=-[\hat{z}\hat{p}_y,\hat{y}]=i\hbar\hat{z}$$

$$[\hat{l}_x,\hat{z}]=[\hat{y}\hat{p}_z-\hat{z}\hat{p}_y,\hat{z}]=[\hat{y}\hat{p}_z,\hat{z}]=-i\hbar\hat{y}$$

同理有：
$$[\hat{l}_y,\hat{x}]=-i\hbar\hat{z},\quad [\hat{l}_y,\hat{z}]=i\hbar\hat{x},\quad [\hat{l}_z,\hat{x}]=i\hbar\hat{y},\quad [\hat{l}_z,\hat{y}]=-i\hbar\hat{x}$$

即 $[\hat{l}_\alpha,\hat{x}_\beta]=i\hbar\varepsilon_{\alpha\beta\gamma}\hat{x}_\gamma$（右手螺旋关系）。

### 角动量与动量的对易关系

$$[\hat{l}_x,\hat{p}_x]=[\hat{y}\hat{p}_z-\hat{z}\hat{p}_y,\hat{p}_x]=0$$

$$[\hat{l}_x,\hat{p}_y]=[\hat{y}\hat{p}_z-\hat{z}\hat{p}_y,\hat{p}_y]=-[\hat{z}\hat{p}_y,\hat{p}_y]=-i\hbar\hat{p}_z$$

$$[\hat{l}_x,\hat{p}_z]=[\hat{y}\hat{p}_z-\hat{z}\hat{p}_y,\hat{p}_z]=[\hat{y}\hat{p}_z,\hat{p}_z]=i\hbar\hat{p}_y$$

同理有：
$$[\hat{l}_y,\hat{p}_x]=-i\hbar\hat{p}_z,\quad [\hat{l}_y,\hat{p}_z]=i\hbar\hat{p}_x,\quad [\hat{l}_z,\hat{p}_x]=i\hbar\hat{p}_y,\quad [\hat{l}_z,\hat{p}_y]=-i\hbar\hat{p}_x$$

### 角动量分量之间的对易关系

$$[\hat{l}_x,\hat{l}_x]=0,\quad [\hat{l}_\alpha,\hat{l}_\alpha]=0\quad(\alpha=x,y,z)$$

$$[\hat{l}_x,\hat{l}_y]=[\hat{y}\hat{p}_z-\hat{z}\hat{p}_y,\hat{z}\hat{p}_x-\hat{x}\hat{p}_z]$$

\$\$=[\hat{y}\hat{p}_z,\hat{z}\hat{p}_x]-[\hat{y}\hat{p}_z,\hat{x}\hat{p}_z]+[\hat{z}\hat{p}_y,\hat