# 一维束缚态

在一维情况下，$A_4=E_4$ 简化为：$\left[-\frac{\hbar^2}{2\mu}\frac{d^2}{dx^2}+V(x)\right]\psi(x)=E\psi(x)$

## 定理1（势函数不连续时）

设 $V(x)=V_1$，$x<a$；$V(x)=V_2$，$x>a$，在 $x=a$ 处不连续，有一个跳跃。当 $V_1-V_2$ 有限时，能量本征函数 $\psi(x)$ 及其导函数 $\psi'(x)=\frac{d\psi}{dx}$ 在 $a$ 点是连续的。

- $\psi(x)$ 本身连续是因为概率幅的连续性问题（$\psi(x)$ 是概率波！）
- $|\psi(x)|<1$，$E\to 0$ 时右式 $\to 0$
- **思路2：反证法**，若 $\psi'(x)$ 不连续，则 $\psi''(x)$ 含冲击项，不符合薛定谔方程
- **思路3：** $\frac{\partial P(x,t)}{\partial t}+\frac{\partial j(x,t)}{\partial x}=0$，$\rho=\psi^*\psi=|\psi|^2$，$j=-\frac{i\hbar}{2\mu}(\psi^*\nabla\psi-\psi\nabla\psi^*)$，连续 $\Rightarrow \psi,\psi'$ 连续

## 一维半无限深方势阱

$$V(x)=\begin{cases}\infty, & x<0 \\ 0, & 0<x<a \\ V_0, & x>a\end{cases}$$

定态薛定谔方程：$-\frac{\hbar^2}{2\mu}\frac{d^2\psi}{dx^2}+V(x)\psi(x)=E\psi(x)$

- $x<0$ 区域：$\because V(x)=\infty$，物理上不允许粒子在此区域出现，故有 $\psi(x)=0$（$x<0$）
- 由 $\psi(0)=0$，则 $\psi(x)=A\sin kx$
- $x>a$ 区域：$\psi''(x)-\frac{2\mu}{\hbar^2}(V_0-E)\psi(x)=0$，令 $\beta=\sqrt{\frac{2\mu(V_0-E)}{\hbar^2}}$，则 $\psi(x)=Be^{\beta x}+Ce^{-\beta x}$
- $\because \psi(x)\to 0$（$x\to\infty$），若 $\beta$ 为虚数即 $V_0<E$，$\psi(x)$ 周期振荡不满足束缚态，故仅考虑 $\beta$ 为实数且 $>0$
- $x\to\infty$ 时 $e^{\beta x}\to\infty$，$\therefore C=0$，$\psi(x)=Be^{-\beta x}$
- $\psi(a)=Be^{-\beta a}=A\sin ka$，$\psi'(a)=-\beta Be^{-\beta a}=kA\cos ka$

于是有：

$$k\cot ka=-\beta,\quad \beta=\sqrt{\frac{2\mu(V_0-E)}{\hbar^2}}$$

且 $\cot ka<0$。**能量满足超越方程**：

$$E=\frac{\hbar^2 k^2}{2\mu}\left[1-\cos(2ka)\right],\quad \cot(ka)<0$$

能量是量子化的。

## 一维束缚态（续）

⇒ $A_n = \left[ a + \frac{\sin^2(k_n a)}{k_n} \right]^{-1/2}$，$\psi_n(x) = A_n \sin(k_n x)$，$0 < x < a$；$\psi_n(x) = 0$，$x < 0$

$B_n = \left[ a - \frac{\sin(2k_n a)}{2k_n} + \frac{\sin^2(k_n a)}{k_n} \right]^{-1/2}$，$\psi_n(x) = B_n e^{-k_n x}$，$x > a$。一个 $E_n$ 对应一个 $\psi_n$。

## 一维谐振子

势能：$V(x) = \frac{1}{2} k x^2 = \frac{1}{2} \mu \omega^2 x^2$（由 $-kx = m\ddot{x}$，$\ddot{x} + \omega^2 x = 0$，$\omega^2 = \frac{k}{\mu}$）

薛定谔方程：
$$
\left[ -\frac{\hbar^2}{2\mu} \frac{d^2}{dx^2} + \frac{1}{2} \mu \omega^2 x^2 \right] \psi(x) = E \psi(x)
$$

令 $\alpha = \sqrt{\frac{\mu \omega}{\hbar}}$，$s = \alpha x$，记 $\psi(x) = \phi(s) = \phi(\alpha x)$，于是：
$$
\frac{d^2 \phi}{ds^2} + (\lambda - s^2) \phi(s) = 0
$$

为“消除”$s^2$ 项，试探设 $\phi(s) = e^{-s^2/2} H(s)$，代入得：
$$
\frac{d^2 H}{ds^2} - 2s \frac{dH}{ds} + (\lambda - 1) H(s) = 0
$$

$\phi(s)$ 有界（平方可积）解，仅当 $\lambda = 2n + 1$ 时，$H_n(s)$ 有 $\phi(s) \to 0$ 的解，$H(s) = H_n(s) = (-1)^n e^{s^2} \frac{d^n}{ds^n} e^{-s^2}$。

正交归一性：
$$
\int_{-\infty}^{\infty} H_m(s) H_n(s) e^{-s^2} ds = \sqrt{\pi} \, 2^n n! \, \delta_{mn}
$$

归一化波函数：
$$
\phi_n(s) = N_n e^{-s^2/2} H_n(s), \quad N_n^2 \int e^{-s^2} H_n(s) H_n(s) ds = 1, \quad N_n = \left( \frac{\alpha}{\sqrt{\pi} \, 2^n n!} \right)^{1/2}
$$

**能量分立化**：
$$
E_n = \left( n + \frac{1}{2} \right) \hbar \omega, \quad \psi_n(x) = N_n e^{-\alpha^2 x^2 / 2} H_n(\alpha x)
$$

### 补充：方程 $\frac{d^2 H(s)}{ds^2} - 2s \frac{dH(s)}{ds} + (\lambda - 1) H(s) = 0$ 的两种解法

**① 幂级数解法，构造递推的系数关系**

设 $H(s) = \sum_j a_j s^j$，代入得递推关系：
$$
(j+2)(j+1) a_{j+2} - 2j a_j + (\lambda - 1) a_j = 0
$$
即：
$$
(j+2)(j+1) a_{j+2} + (-2j + \lambda - 1) a_j = 0
$$

$s \to \infty$ 时，$\phi(s)$ 按 $e^{s^2}$ 量级增长，不可积。级数存在（只有）有限项：$a_n \neq 0$，$a_{n+2} = 0$，即 $\lambda = 2n + 1$。

从而有 $a_{j-2} = \frac{2j - \lambda + 1}{j(j-1)} a_j$，多项式 $H(s)$ 只能含奇数项或偶数项，系数由高次项推至低次项。

**② 方程可变化为**：
$$
\frac{d^2 H}{ds^2} - 2s \frac{dH}{ds} + 2n H(s) = 0
$$
其解为厄米多项式 $H_n(s)$。

通项公式：
$$
H_n(s) = \sum_{k=0}^{\lfloor n/2 \rfloor} \frac{(-1)^k n!}{k! (n-2k)!} (2s)^{n-2k}
$$
（可通过递推 + 母函数求解）

$H_n(s)$ 满足递推关系：
$$
H_n'(s) - 2s H_n'(s) + 2n H_n(s) = 0
$$

母函数：
$$
w(t, x) = e^{2tx - t^2}, \quad \frac{\partial w(t, x)}{\partial t} + 2(t - x) w(t, x) = 0
$$

## 一维束缚态

（接上页）

4中

）=2）（2）△=

heBu+）u+=△e+

=[J）A++()=Qs+S）S]-=1

-（)）+))()

2²[s（sθ)((]

一（r）(）E）(sn $+s\r0$ ²θL \$∂^{2

∴Rn（r²）+CE-V(]=-r[s（snθ+

**径向方程：** $[r²d]+(E-V(r)-R(r)=0$

**角向方程：** $sinθ$(sinθr8) 80 )+5m{\$

①考虑角向方程. Y(θ，φ)=(0)(4)

$sinθa[snθ](+()=-λ④()() sm]++△sn²8=$

$a[sθa]+λsim²θ0=-φ1=m²$

$a^{2}$ +m^{2}φ()=0⇒Φm（p)=\eim

对于勒让德方程 $sine为[sinθd]+(λ-m)④(θ)=0$，为使④(0)在区间[O，π]有限，入只能取

a(asP()

**m1≤l时才有(θ)≠0 ⇒m=0，±1，\$.，±l.**

（θ)（0）sinθdθ=S，Bm= (L-1m|)!(2(+1) 2(l+1ml) ，Ym（θ）=m（)Φm（4）=N1-)（θ)]

(L-1m|)|(2l+1) 4π(+m 球谐函数满足正交关系：Y(θ，Φ)Ym(θ，)sinθdθdφ=δδmm

个的其同本征太

# 氢原子

径向方程：

$$\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right)+\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{r}\right)-\frac{l(l+1)}{r^2}\right]R(r)=0$$

其中 $V(r)=-\frac{e^2}{r}$，令 $k=\frac{\sqrt{-2\mu E}}{\hbar}$，则方程为：

$$\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right)+\left(\frac{2\mu e^2}{\hbar^2 r}-k^2\right)-\frac{l(l+1)}{r^2}\right]R(r)=0$$

引入约化径向波函数 $u(r)=rR_l(r)$，则 $u(r)$ 满足：

$$\left[\frac{d^2}{dr^2}+\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{r}\right)-\frac{l(l+1)}{r^2}\right]u(r)=0$$

∵ $V(r)<0$，$R_l(r)\to 0$，$r\to\infty$ 时薛定谔方程约为 $\frac{d^2u}{dr^2}+k^2u=0$，若 $E>0$，$u(r)$ 呈振荡形式，不满足束缚态，则 $E<0$。从能量角度分析，$E=V+K$，$K<V$，$E<0$。核与电子“双星模型”。

于是方程化为：

$$\left[\frac{d^2}{d\rho^2}+\frac{\beta}{\rho}-\frac{l(l+1)}{\rho^2}-\frac{1}{4}\right]u(\rho)=0$$

$\rho\to\infty$ 时，方程近似为 $\frac{d^2u}{d\rho^2}-\frac{1}{4}u(\rho)=0$，$u(\rho)\sim e^{-\rho/2}$。

$\rho\to 0$ 时，方程近似为 $\frac{d^2u}{d\rho^2}-\frac{l(l+1)}{\rho^2}u(\rho)=0$，$u(\rho)\sim \rho^{l+1}$。

利用渐进解，设 $u(\rho)=\rho^{l+1}e^{-\rho/2}v(\rho)$。

$v(\rho)$ 满足方程：

$$\rho v''+(2l+2-\rho)v'+[\beta-(l+1)]v(\rho)=0$$

为**合流超几何方程**。

$v(\rho)$ 有多项式解的条件是 $\beta-l-1=n_r$，即 $\beta=l+1+n_r$（$n_r=0,1,2,\dots$）。

令 $n=l+1+n_r$，$n=1,2,\dots$，则 $k^2=\frac{\mu e^4}{2\hbar^4 n^2}$，$\therefore E_n=-\frac{\mu e^4}{2\hbar^2 n^2}$。

$l$ 的取值为 $0,1,\dots,n-1$；$m$ 的取值为 $-l,-(l-1),\dots,0,\dots,l$。能量本征态由 $(n,l,m)$ 表征。

**氢离子轨道角动量的取值**：$L^2=l(l+1)\hbar^2$，$l=0,1,2,\dots$

**氢离子轨道角动量 $z$ 方向的取值**：$L_z=m\hbar$，$L_z Y_{lm}=m\hbar Y_{lm}$

径向波函数：

$$R_{nl}(r)=N_{nl}\rho^l e^{-\rho/2}L_{n+l}^{2l+1}(\rho)$$

归一化条件：

$$\int_0^\infty |R_{nl}(r)|^2 r^2 dr = 1$$

**能级简并**：$n=n_r+l+1$，能级简并度 $\sum_{l=0}^{n-1}(2l+1)=n^2$。

**径向位置概率分布**：在 $(r, r+dr)$ 内概率为：

$$r^2 dr \int |\psi_{nlm}(r,\theta,\phi)|^2 \sin\theta\, d\theta\, d\phi = r^2 |R_{nl}(r)|^2 dr = |u_{nl}(r)|^2 dr$$

## 概率密度角度分布

概率密度角度分布在 $(\theta, \varphi)$ 方向的立体角 $d\Omega$ 中电子的概率为 $|Y_{lm}(\theta, \varphi)|^2 d\Omega = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$。

关于径向概率分布：$P = r^2 R^2 \sin\theta \, dr \, d\theta \, d\varphi$。

关于概率密度角度分布：$P(\theta, \theta+d\theta; \varphi, \varphi+d\varphi) = \int |\psi|^2 r^2 \sin\theta \, dr \, d\theta \, d\varphi = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$。

## 电流分布与磁矩

电流密度 = 电荷 × 概率流密度：$\vec{j}_c = (-e) \cdot \left[ -\frac{i\hbar}{2m} (\psi^* \nabla \psi - \psi \nabla \psi^*) \right]$。

$\nabla = \hat{r} \frac{\partial}{\partial r} + \hat{\theta} \frac{1}{r} \frac{\partial}{\partial \theta} + \hat{\varphi} \frac{1}{r\sin\theta} \frac{\partial}{\partial \varphi}$。

$\psi_{nlm}(r, \theta, \varphi) = N R_{nl}(r) P_l^m(\cos\theta) e^{im\varphi}$，$R_{nl}(r)$、$P_l^m(\cos\theta)$ 为实函数，则 $j_r = 0$，$j_\theta = 0$。

$j_\varphi = \frac{e\hbar m}{2m_e r \sin\theta} |\psi|^2 = \frac{e\hbar m}{2m_e r \sin\theta} |R_{nl} P_l^m|^2$。

$\vec{j}_\varphi$ 是围绕 $z$ 轴的许多环形电流（在 $x$-$y$ 平面），$d\vec{\mu} = dI \times \vec{S}$。

$dI = j_\varphi \times (r d\theta) \times dr$，截面面积：$(r d\theta) \times dr$，电流 $= j_\varphi \times r \, d\theta \, dr$。

$d\mu = dI \times \pi (r\sin\theta)^2 = j_\varphi \times r \, d\theta \, dr \times \pi r^2 \sin^2\theta$。

## 碱金属原子

碱金属原子的势能为：

$$V(r)=-\frac{e^2}{r}-\frac{ke^2}{r^2} \quad (\text{碱金属原子})$$

其中 $a_0$ 为玻尔半径。

径向方程为：

$$\left[\frac{d^2}{dr^2}+\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{r}+\frac{ke^2}{r^2}\right)-\frac{l(l+1)}{r^2}\right]R_l(r)=0$$

即：

$$\left[\frac{d^2}{dr^2}+\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{r}\right)+\frac{2\mu ke^2}{\hbar^2 r^2}-\frac{l(l+1)}{r^2}\right]R(r)=0$$

令 $l(l+1)-2\lambda=l'(l'+1)$，则类比氢原子，有：

$$E_n=-\frac{\mu e^4}{2\hbar^2 n^2}, \quad n=n_r+l'+1$$

其中：

$$l'=-\frac{1}{2}+\sqrt{\left(l+\frac{1}{2}\right)^2-2\lambda}=-\frac{1}{2}+\left(l+\frac{1}{2}\right)\sqrt{1-\frac{2\lambda}{\left(l+\frac{1}{2}\right)^2}}$$

$l'$ 与 $l$ 有关，能级简并度为 $2l'+1$。

## 电磁场中电荷粒子的哈密顿量

在电磁场中，存在带电量为 $q$，质量为 $m$ 的粒子，粒子受力：

$$\mathbf{F}=q\mathbf{E}+q\mathbf{v}\times\mathbf{B}$$

由 $\nabla\cdot\mathbf{B}=0$，则引入 $\mathbf{A}$ 为矢势：

$$\mathbf{B}=\nabla\times\mathbf{A}, \quad \mathbf{E}=-\nabla\phi-\frac{\partial\mathbf{A}}{\partial t}$$

其中 $\phi$ 为电势。

$$\nabla\times\mathbf{B}=\nabla\times(\nabla\times\mathbf{A})=\nabla(\nabla\cdot\mathbf{A})-\nabla^2\mathbf{A}$$

$$\mathbf{B}=\begin{pmatrix} B_x \\ B_y \\ B_z \end{pmatrix}, \quad \mathbf{v}\times\mathbf{B}=\begin{vmatrix} \hat{i} & \hat{j} & \hat{k} \\ v_x & v_y & v_z \\ B_x & B_y & B_z \end{vmatrix}$$

$$F_x=q\left[-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+v_y\left(\frac{\partial A_y}{\partial x}-\frac{\partial A_x}{\partial y}\right)-v_z\left(\frac{\partial A_x}{\partial z}-\frac{\partial A_z}{\partial x}\right)\right]$$

考虑 $A_x(x,y,z,t)$，则：

$$\frac{dA_x}{dt}=\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}$$

故：

$$F_x=q\left[-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}\right]=q\left(-\frac{\partial\phi}{\partial x}-\frac{dA_x}{dt}+\frac{\partial A_x}{\partial x}\dot{x}\right)$$

由 $\mathbf{F}=\frac{d}{dt}(m\mathbf{v})$，则：

$$\frac{d}{dt}(m\dot{x}+qA_x)=q\left(-\frac{\partial\phi}{\partial x}\right)+q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})$$

令 $U=q(\phi-\mathbf{A}\cdot\mathbf{v})$，则：

$$\frac{\partial U}{\partial x}=q\frac{\partial\phi}{\partial x}-q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})=-q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})+q\frac{\partial\phi}{\partial x}$$

$$\frac{\partial U}{\partial \dot{x}}=-qA_x, \quad \frac{\partial U}{\partial \dot{y}}=-qA_y, \quad \frac{\partial U}{\partial \dot{z}}=-qA_z$$

由拉格朗日方程：

$$\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{x}}\right)-\frac{\partial L}{\partial x}=F_x=-q\frac{\partial}{\partial x}(\phi-\mathbf{A}\cdot\mathbf{v})$$

其中动能 $T=\frac{1}{2}m\dot{x}^2$。

$$\frac{d}{dt}\left[\frac{\partial}{\partial \dot{x}}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})\right]-\frac{\partial}{\partial x}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})=0$$

即：

$$\frac{d}{dt}\left(\frac{\partial}{\partial \dot{x}}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})\right)-\frac{\partial}{\partial x}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})=0$$

对 $y$、$z$ 分量同理。

$$\frac{\partial L}{\partial \dot{x}}=m\dot{x}+qA_x$$

## 哈密顿量

$$H = -L = (mv + qA) \cdot v - \frac{1}{2}mv^2 - (-V \cdot A) = \frac{1}{2}mv^2 + q\varphi = \frac{1}{2m}(P - qA)^2 + q\varphi$$

考虑系统中心力，$H = \frac{1}{2m}p^2 - \frac{A}{r} + V(r)$

## 补充：坐标系变换

### ① 典型空间中的度规

两个面的通量之差为 $\left( \frac{\partial P}{\partial x} \right) du\,dv\,dw$，即 $\frac{\partial P}{\partial x} du\,dv\,dw$。

**二维空间**，线元 $ds^2 = (dx)^2 + (dy)^2 = (dx, dy) \begin{pmatrix} dx \\ dy \end{pmatrix} = g_{ij} dx^i dx^j$

若取极坐标系 $r, \varphi$，$x = r\cos\varphi$，$y = r\sin\varphi$，则

$$ds^2 = (dr\cos\varphi - r\sin\varphi\, d\varphi)^2 + (dr\sin\varphi + r\cos\varphi\, d\varphi)^2 = dr^2 + r^2 d\varphi^2$$

$$ds^2 = g_{ij} dx^i dx^j, \quad G = \begin{pmatrix} 1 & 0 \\ 0 & r^2 \end{pmatrix}$$

**三维欧氏空间**，线元 $ds^2 = (dx)^2 + (dy)^2 + (dz)^2 = \sum_{ij} g_{ij} dx^i dx^j$，$g_{ij} = \delta_{ij} = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$

若取球坐标，即 $\{x^1, x^2, x^3\} = \{r, \theta, \varphi\}$，$x = r\sin\theta\cos\varphi$，$y = r\sin\theta\sin\varphi$，$z = r\cos\theta$，则

$$G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2\sin^2\theta \end{pmatrix}$$

### 梯度算子

$h_i = \sqrt{g_{ii}}$，在 $q_2, q_3$ 不变而 $q_1$ 相差微小变量时，线元 $(ds)^2 = h_1^2 (dq_1)^2$（正交系）。

对标量函数 $u(q_1, q_2, q_3)$，在 $u$ 增长方向的梯度 $(\nabla u)_i = \frac{1}{h_i}\frac{\partial u}{\partial q_i} \hat{e}_i$

**笛卡尔坐标系中的表示**

事实上，考虑 $\nabla u = \frac{\partial u}{\partial x}\hat{e}_x + \frac{\partial u}{\partial y}\hat{e}_y + \frac{\partial u}{\partial z}\hat{e}_z$

于是有 $\left(\frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z}\right) = \left(\frac{\partial u}{\partial r}, \frac{\partial u}{\partial \theta}, \frac{\partial u}{\partial \varphi}\right) \frac{\partial(u, v, w)}{\partial(x, y, z)}$

即

$$\left(\frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z}\right) = \left(\frac{\partial u}{\partial r}, \frac{\partial u}{\partial \theta}, \frac{\partial u}{\partial \varphi}\right) \frac{\partial(u, v, w)}{\partial(x, y, z)} \times \frac{\partial(x, y, z)}{\partial(u, v, w)}$$

$$\frac{\partial(u, v, w)}{\partial(x, y, z)} \cdot \frac{\partial(x, y, z)}{\partial(u, v, w)} = 1$$

## 3 散度定理

向量场在闭合曲面的通量等于向量场的散度在曲面包围区域的体积分。

考虑平行于 $d$ 的四个面，在剩下两面中一个面的通量为：

两个面的通量之差为 $\left( \frac{\partial J}{\partial u} dudv \right) dw = \frac{\partial J}{\partial u} dudvdw$

同理，另外两个通量差为 $\frac{\partial J}{\partial v} dudvdw$，$\frac{\partial J}{\partial w} dudvdw$

$$\therefore (\nabla \cdot \mathbf{F}) V = (\nabla \cdot \mathbf{F}) J dudvdw = \left( \frac{\partial}{\partial u} + \frac{\partial}{\partial v} + \frac{\partial}{\partial w} \right) J dudvdw$$

$$\nabla \cdot \mathbf{F} = \left[ \frac{\partial}{\partial u} + \frac{\partial}{\partial v} + \frac{\partial}{\partial w} \right] |J| = \frac{1}{H_u H_v H_w} \left[ \frac{\partial}{\partial u}(H_v H_w F_u) + \frac{\partial}{\partial v}(H_u H_w F_v) + \frac{\partial}{\partial w}(H_u H_v F_w) \right]$$

如 $(u, v, w) = (r, \theta, \phi)$，则

$$\nabla \cdot \mathbf{F} = \frac{1}{r^2 \sin\theta} \left[ \frac{\partial}{\partial r}(r^2 \sin\theta \, F_r) + \frac{\partial}{\partial \theta}(\sin\theta \, F_\theta) + \frac{\partial}{\partial \phi}(r F_\phi) \right]$$

## ④ 旋度

$$\text{rot } \mathbf{a} = \lim_{S \to 0} \frac{\oint \mathbf{a} \cdot d\mathbf{s}}{S}$$

$$\mathbf{a} = a_u \mathbf{e}_u + a_v \mathbf{e}_v + a_w \mathbf{e}_w$$

考虑 $\text{rot } \mathbf{a}$ 在 $u$ 轴上的投影，取 $\mathbf{n}$ 为正方向，$S$ 面是 $u = \text{常数}$，曲面 $S$ 中的曲线 $L$ 设为 $M_1 M_2 N_2 N_1$。

$$\int_{M_1 M_2} \mathbf{a} \cdot d\mathbf{s} = \mathbf{a}(u, v, w) \cdot d\mathbf{s} = \mathbf{a}(u, v, w) \cdot \mathbf{H}_v dv = a_v(u, v, w) H_v(u, v, w) dv$$

其中 $N_1(u, v+\Delta v, w+\Delta w)$，$N_2(u, v+\Delta v, w)$，$M_1(u, v, w)$，$M_2(u, v+\Delta v, w)$。

$$\int_{M_2 N_2} \mathbf{a} \cdot d\mathbf{s} = \mathbf{a}(u, v+\Delta v, w) \cdot d\mathbf{s} = \mathbf{a}(u, v+\Delta v, w) \cdot \mathbf{H}_w dw = a_w(u, v+\Delta v, w) H_w(u, v+\Delta v, w) dw$$

$$\int_{N_2 N_1} \mathbf{a} \cdot d\mathbf{s} = \mathbf{a}(u, v, w+\Delta w) \cdot d\mathbf{s} = -\mathbf{a}(u, v, w+\Delta w) \cdot \mathbf{H}_v dv = -a_v(u, v, w+\Delta w) H_v(u, v, w+\Delta w) dv$$

$$\int_{N_1 M_1} \mathbf{a} \cdot d\mathbf{s} = -\mathbf{a}(u, v, w) \cdot \mathbf{H}_w dw = -a_w(u, v, w) H_w(u, v, w) dw$$

则

$$\oint \mathbf{a} \cdot d\mathbf{s} = \left[ \frac{\partial(a_w H_w)}{\partial v} - \frac{\partial(a_v H_v)}{\partial w} \right] dv dw = (\text{rot } \mathbf{a})_u \, dv dw = \frac{1}{H_v H_w} \left[ \frac{\partial(a_w H_w)}{\partial v} - \frac{\partial(a_v H_v)}{\partial w} \right] H_u H_v H_w \, dv dw$$

$$(\text{rot } \mathbf{a})_u = \frac{1}{H_v H_w} \left[ \frac{\partial(a_w H_w)}{\partial v} - \frac{\partial(a_v H_v)}{\partial w} \right]$$

∴(D·F)V = (D·J) du dv dw = u(D·dudvdw) + ( )dudvdw + (J)dudvdw

考虑 rot a 在 u 轴上的投影，取 n 为正方向，S 面是 u = 常数，曲面 S 中的曲线 L 设为 $MM_2M_1$。

沿 $MM_2$：$\int_{M}^{M_2} \mathbf{a} \cdot d\mathbf{s} = a(u, v, w) \cdot H_v dv = a_v(u, v, w) H_v(u, v, w) dv$

沿 $M_2N_2$：$\int_{M_2}^{N_2} \mathbf{a} \cdot d\mathbf{s} = a(u, v+dv, w) H_w dw = a_w(u, v+dv, w) H_w(u, v+dv, w) dw$

沿 $N_2N_1$：$\int_{N_2}^{N_1} \mathbf{a} \cdot d\mathbf{s} = -a(u, v, w+dw) H_v dv = -a_v(u, v, w+dw) H_v(u, v, w+dw) dv$

沿 $N_1M_1$：$\int_{N_1}^{M_1} \mathbf{a} \cdot d\mathbf{s} = -a(u, v, w) H_w dw = -a_w(u, v, w) H_w(u, v, w) dw$

则 $\oint \mathbf{a} \cdot d\mathbf{s} = \frac{\partial(a_w H_w)}{\partial v} dv dw - \frac{\partial(a_v H_v)}{\partial w} dv dw = \frac{1}{H_u H_v H_w} \left[ \frac{\partial(a_w H_w)}{\partial v} - \frac{\partial(a_v H_v)}{\partial w} \right] H_u H_v H_w \, dv dw$

因此 $(\text{rot } \mathbf{a})_u = \frac{1}{H_v H_w} \left[ \frac{\partial(a_w H_w)}{\partial v} - \frac{\partial(a_v H_v)}{\partial w} \right]$