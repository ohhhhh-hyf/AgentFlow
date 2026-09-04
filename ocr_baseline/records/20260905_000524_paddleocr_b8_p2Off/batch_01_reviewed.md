### 一维束缚态

在一维情况下，$\hat{A}_4 = E_4$ 简化为：

$$
\left[-\frac{\hbar^2}{2\mu}\frac{d^2}{dx^2} + V(x)\right]\psi(x) = E\psi(x)
$$

其中，$\psi(x)$ 为能量本征函数。

#### 定理 1（势函数不连续时）

设 $V(x) = V_1$（$x < a$），$V(x) = V_2$（$x > a$），在 $x = a$ 处不连续，有一个跳跃。当 $V_1 - V_2$ 有限时，能量本征函数 $\psi(x)$ 及其导函数 $\psi'(x) = \frac{d\psi}{dx}$ 在 $a$ 点是连续的。

- $\psi(x)$ 本身连续是因为概率幅的连续性问题（$\psi(x)$ 是概率波！）
- $|\psi(x)| < \infty$，当 $E \to 0$ 时右式 $\to 0$
- **思路 2**：反证法，若 $\psi'(x)$ 不连续，则 $\psi''(x)$ 含冲击项，不符合薛定谔方程
- **思路 3**：连续性方程 $\frac{\partial \rho}{\partial t} + \frac{\partial j}{\partial t} = 0$，其中 $\rho = \psi^*\psi = |\psi|^2$，$j = -\frac{i\hbar}{2\mu}(\psi^*\nabla\psi - \psi\nabla\psi^*)$。连续 $\Rightarrow \psi, \psi'$ 连续

---

时，能量本征函数 $\psi(x)$ 及其导函数 $\psi'(x)$ 在 $a$ 点是连续的。  
$\psi(x)$ 本身连续是因为概率幅的连续性问题（$\psi(x)$ 是概率波！）  
由 $|\psi(x)| < \infty$，当 $E \to 0$ 时右式 $\to 0$。  
思路2：反证法，若 $\psi'(x)$ 不连续，则 $\psi(x)$ 含冲击项，不符合薛定谔方程。  
一维半无限深方势阱

### 一维半无限深方势阱

$$
V(x) = \begin{cases}
\infty, & x < 0 \\
0, & 0 < x < a \\
V_0, & x > a
\end{cases}
$$

定态薛定谔方程：

$$
-\frac{\hbar^2}{2\mu}\frac{d^2\psi}{dx^2} + V(x)\psi(x) = E\psi(x)
$$

**分区求解：**

1. **$x < 0$ 区域**：$\because V(x) = \infty$，物理上不允许粒子在此区域出现，故有 $\psi(x) = 0 \quad (x < 0)$。

2. **$0 < x < a$ 区域**：$\psi(0) = 0$，则 $\psi(x) = A\sin(kx)$。

3. **$x > a$ 区域**：有方程 $\psi''(x) - \frac{2\mu}{\hbar^2}(V_0 - E)\psi(x) = 0$。令 $\beta = \frac{\sqrt{2\mu(V_0 - E)}}{\hbar}$，则 $\psi(x) = Be^{\beta x} + Ce^{-\beta x}$。

$\because \psi(x) \to 0$ 当 $x \to \infty$，若 $\beta$ 为虚数（即 $V_0 < E$），$\psi(x)$ 周期振荡不满足束缚态条件，故仅考虑 $\beta$ 为实数且 $> 0$。

当 $x \to \infty$ 时 $e^{\beta x} \to \infty$，$\therefore C = 0$，$\psi(x) = Be^{-\beta x}$。

**边界条件（$x = a$ 处连续）：**

$$
\psi(a) = Be^{-\beta a} = A\sin(ka), \quad \psi'(a) = -\beta Be^{-\beta a} = kA\cos(ka)
$$

于是有：

$$
k\cot(ka) = -\beta, \quad \beta = \frac{\sqrt{2\mu(V_0 - E)}}{\hbar}
$$

且 $\cot(ka) < 0$。

**能量满足超越方程：**

$$
E = \frac{\hbar^2 k^2}{2\mu} = \frac{\hbar^2}{2\mu a^2}(ka)^2, \quad \text{且} \quad \cot(ka) < 0
$$

能量是量子化的。

## 一维束缚态（续）

⇒ $A_n = \left[ a + \frac{\sin^2 k_n a}{?} \right]^{-1/2}$，$\psi_n(x) = A_n \sin(k_n x)$，$0 < x < a$；$\psi = 0$，$x < 0$

$B_n = \left[ a - \frac{\sin(2k_n a)}{2k_n} + \frac{\sin^2 k_n a}{?} \right]^{-1/2}$，$\psi_n(x) = B_n e^{-\kappa x}$，$x > a$。一个 $E_n$ 对应一个 $\psi_n$。

## 一维谐振子

势能：$V(x) = \frac{1}{2} k x^2 = \frac{1}{2} \mu \omega^2 x^2$（$-\frac{dV}{dx} = -kx = \mu \ddot{x}$，$\ddot{x} + \omega^2 x = 0$，$\omega^2 = \frac{k}{\mu}$）

薛定谔方程：$\left[ -\frac{\hbar^2}{2\mu} \frac{d^2}{dx^2} + \frac{1}{2} \mu \omega^2 x^2 \right] \psi(x) = E \psi(x)$

令 $\alpha = \sqrt{\frac{\mu \omega}{\hbar}}$，$s = \alpha x$，记 $\psi(x) = \phi(s) = \phi(\alpha x)$，于是 $\left( -\frac{d^2}{ds^2} + s^2 \right) \phi(s) = \lambda \phi(s)$

即 $\frac{d^2 \phi(s)}{ds^2} + (\lambda - s^2) \phi(s) = 0$

为“消除”$s^2$ 项，试探设 $\phi(s) = e^{-s^2/2} H(s)$，代入得 $-s \frac{dH}{ds} + \frac{d^2 H}{ds^2} + (\lambda - 1) H(s) = 0$

$\phi(s)$ 有界，仅当 $\lambda = 2n + 1$ 时，$H_n(s)$ 有有界解，$H(s) = H_n(s) = (-1)^n e^{s^2} \frac{d^n}{ds^n} e^{-s^2}$

正交归一性：$\int_{-\infty}^{\infty} H_m(s) H_n(s) e^{-s^2} ds = \sqrt{\pi} 2^n n! \, \delta_{mn}$

$\phi_n(s) = N_n e^{-s^2/2} H_n(s)$，$N_n^2 \int e^{-s^2} H_n^2(s) ds = 1$，$N_n = \left( \frac{\alpha}{\sqrt{\pi} 2^n n!} \right)^{1/2}$

**能量分立化**：$E_n = \left( n + \frac{1}{2} \right) \hbar \omega$，$\psi_n(x) = N_n e^{-\alpha^2 x^2 / 2} H_n(\alpha x)$

### 补充：方程 $\frac{d^2 H(s)}{ds^2} - 2s \frac{dH(s)}{ds} + (\lambda - 1) H(s) = 0$ 的两种解法

**① 幂级数解法，构造递推的系数关系**

设 $H(s) = \sum_j a_j s^j$，代入得 $a_{j+2} (j+2)(j+1) - a_j (2j + 1 - \lambda) = 0$，即 $\frac{a_{j+2}}{a_j} = \frac{2j + 1 - \lambda}{(j+2)(j+1)}$

若级数无穷，则 $H(s) \sim c e^{s^2}$，$\phi(s)$ 按 $e^{s^2/2}$ 量级增长，不可积。级数存在有限项（只有有限项 $a_n \neq 0$，$a_{n+2} = 0$），即 $\lambda = 2n + 1$。

从而有 $a_{j+2} = \frac{2(j - n)}{(j+2)(j+1)} a_j$，多项式 $H(s)$ 只能含奇数项或偶数项，系数由高次项推至低次项。

**② 方程可变化为 $\frac{d^2 H}{ds^2} - 2s \frac{dH}{ds} + 2n H(s) = 0$，其解为厄米多项式 $H_n(s)$。**

$H_n(s) = \sum_{k=0}^{\lfloor n/2 \rfloor} \frac{(-1)^k n!}{k! (n-2k)!} (2s)^{n-2k}$（可通过递推 + 母函数求解）

$H_n(s)$ 满足：$H_n''(s) - 2s H_n'(s) + 2n H_n(s) = 0$。母函数 $w(t, x) = e^{2tx - t^2}$，满足 $\frac{\partial w(t, x)}{\partial t} + 2(t - x) w(t, x) = 0$。

## 一维束缚态（续）

### 分离变量法求解

设 $\psi(r,\theta,\varphi)=R(r)\Theta(\theta)\Phi(\varphi)$，代入薛定谔方程并分离变量：

$$\frac{1}{R}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right)+\frac{2\mu r^2}{\hbar^2}[E-V(r)] = l(l+1)$$

$$\frac{1}{\Theta\sin\theta}\frac{d}{d\theta}\left(\sin\theta\frac{d\Theta}{d\theta}\right)+\frac{1}{\Phi\sin^2\theta}\frac{d^2\Phi}{d\varphi^2} = -l(l+1)$$

**径向方程：**

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right)+\left[\frac{2\mu}{\hbar^2}(E-V(r))-\frac{l(l+1)}{r^2}\right]R(r)=0$$

**角向方程：**

$$\frac{1}{\sin\theta}\frac{d}{d\theta}\left(\sin\theta\frac{d\Theta}{d\theta}\right)+\left[l(l+1)-\frac{m^2}{\sin^2\theta}\right]\Theta(\theta)=0$$

---

### ① 角向方程的求解

设 $Y(\theta,\varphi)=\Theta(\theta)\Phi(\varphi)$，分离变量：

$$\frac{1}{\Phi}\frac{d^2\Phi}{d\varphi^2}=-m^2$$

$$\frac{d^2\Phi}{d\varphi^2}+m^2\Phi(\varphi)=0 \Rightarrow \Phi_m(\varphi)=e^{im\varphi}$$

对于勒让德方程：

$$\frac{1}{\sin\theta}\frac{d}{d\theta}\left(\sin\theta\frac{d\Theta}{d\theta}\right)+\left[\lambda-\frac{m^2}{\sin^2\theta}\right]\Theta(\theta)=0$$

为使 $\Theta(\theta)$ 在区间 $[0,\pi]$ 上有限，**$\lambda$ 只能取 $l(l+1)$**，其中 $l=0,1,2,\dots$

**当 $|m|\le l$ 时才有 $\Theta(\theta)\neq 0$**，即 $m=0,\pm1,\pm2,\dots,\pm l$。

归一化条件：

$$\int_0^\pi |\Theta(\theta)|^2\sin\theta\,d\theta = 1$$

归一化系数：

$$N_{lm} = \sqrt{\frac{(2l+1)(l-|m|)!}{2(l+|m|)!}}$$

球谐函数：

$$Y_{lm}(\theta,\varphi) = N_{lm}P_l^{|m|}(\cos\theta)e^{im\varphi} = \sqrt{\frac{(2l+1)(l-|m|)!}{4\pi(l+|m|)!}}P_l^{|m|}(\cos\theta)e^{im\varphi}$$

**球谐函数满足正交关系：**

$$\int_0^{2\pi}\int_0^\pi Y_{lm}^*(\theta,\varphi)Y_{l'm'}(\theta,\varphi)\sin\theta\,d\theta\,d\varphi = \delta_{ll'}\delta_{mm'}$$

即不同 $(l,m)$ 对应的球谐函数相互正交，构成完备集。

# 氢原子

径向方程：

$$\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right)+\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{4\pi\varepsilon_0 r}\right)-\frac{l(l+1)}{r^2}\right]R(r)=0$$

其中 $V(r)=-\frac{e^2}{4\pi\varepsilon_0 r}$，令 $k=\frac{\sqrt{-2\mu E}}{\hbar}$，则方程为：

$$\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right)+\left(E+\frac{e^2}{4\pi\varepsilon_0 r}\right)-\frac{l(l+1)}{r^2}\right]R(r)=0$$

引入约化径向波函数 $u(r)=rR_l(r)$，则 $u(r)$ 满足：

$$\left[\frac{d^2}{dr^2}+\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{4\pi\varepsilon_0 r}\right)-\frac{l(l+1)}{r^2}\right]u(r)=0$$

**束缚态条件**：$\because V(r)<0$，$R_l(r)\to 0$，$r\to\infty$ 时薛定谔方程约为 $\frac{d^2u}{dr^2}+\frac{2\mu E}{\hbar^2}u=0$，若 $E>0$，$u(r)$ 呈振荡形式，不满足束缚态，则 **$E<0$**。从能量角度分析，$E=V+K$，$K<V$，$E<0$。核与电子构成“双星模型”。

于是方程化为：

$$\left[\frac{d^2}{d\rho^2}+\left(\frac{2}{\rho}-\frac{l(l+1)}{\rho^2}-\frac{1}{4}\right)\right]u(\rho)=0$$

其中 $\rho=\frac{2r}{na_0}$。

$\rho\to\infty$ 时，方程近似为 $\frac{d^2u}{d\rho^2}-\frac{1}{4}u(\rho)=0$，$u(\rho)\sim e^{-\rho/2}$。

$\rho\to 0$ 时，方程近似为 $\frac{d^2u}{d\rho^2}-\frac{l(l+1)}{\rho^2}u(\rho)=0$，$u(\rho)\sim \rho^{l+1}$。

利用渐进解，设 $u(\rho)=\rho^{l+1}e^{-\rho/2}v(\rho)$。

$v(\rho)$ 满足方程：

$$\rho v''+(2l+2-\rho)v'+[\beta-l-1]v(\rho)=0$$

为**合流超几何方程**。

$v(\rho)$ 有多项式解的条件是 $\beta-l-1=n_r$，即 $\beta=l+1+n_r$（$n_r=0,1,2,\dots$）。

令 $n=l+1+n_r$，$n=1,2,3,\dots$，则：

$$\beta=\frac{\mu e^4}{2\hbar^2 k^2}=n \Rightarrow E_n=-\frac{\mu e^4}{2\hbar^2 n^2}=-\frac{13.6\text{ eV}}{n^2}$$

$l$ 的取值为 $0,1,2,\dots,n-1$；$m$ 的取值为 $-l,-(l-1),\dots,0,\dots,l$。能量本征态由 $(n,l,m)$ 表征。

**轨道角动量**：

- 氢原子轨道角动量的取值：$L^2=l(l+1)\hbar^2$，$l=0,1,2,\dots,n-1$
- 氢原子轨道角动量 $z$ 方向的取值：$L_z=m\hbar$，$Y_{lm}$ 满足 $L_z Y_{lm}=m\hbar Y_{lm}$

径向波函数：

$$R_{nl}(r)=N_{nl}\left(\frac{2r}{na_0}\right)^l e^{-r/na_0} L_{n+l}^{2l+1}\left(\frac{2r}{na_0}\right)$$

其中 $N_{nl}$ 为归一化常数。

**归一化条件**：

$$\int_0^\infty |R_{nl}(r)|^2 r^2 dr = 1$$

**能级简并**：$n=n_r+l+1$，能级简并度 $\sum_{l=0}^{n-1}(2l+1)=n^2$。

**径向位置概率分布**：在 $(r, r+dr)$ 内概率为：

$$|\psi_{nlm}|^2 r^2 dr \sin\theta d\theta d\varphi = r^2 |R_{nl}(r)|^2 dr = |u_{nl}(r)|^2 dr$$

## 概率密度与角度分布

概率密度角度分布在 $(\theta, \varphi)$ 方向的立体角 $d\Omega$ 中电子的概率为 $|Y_{lm}(\theta, \varphi)|^2 d\Omega = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$。

关于径向概率分布：$P(r) = r^2 R_{nl}^2(r) \, dr$。

关于概率密度角度分布：$P(\theta, \varphi) \, d\theta \, d\varphi = \int |R_{nl}(r)|^2 r^2 \, dr \cdot |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$。

## 电流分布与磁矩

电流密度 = 电荷 × 概率流密度：$\vec{j}_c = (-e) \cdot \vec{j} = (-e) \cdot \frac{\hbar}{2mi}(\psi^* \nabla \psi - \psi \nabla \psi^*)$。

其中 $\nabla = \hat{r} \frac{\partial}{\partial r} + \hat{\theta} \frac{1}{r} \frac{\partial}{\partial \theta} + \hat{\varphi} \frac{1}{r \sin\theta} \frac{\partial}{\partial \varphi}$。

$\psi_{nlm}(r, \theta, \varphi) = N R_{nl}(r) P_l^m(\cos\theta) e^{im\varphi}$，其中 $P_l^m(\cos\theta)$ 为实函数，则 $j_r = 0$，$j_\theta = 0$。

$j_\varphi = \frac{\hbar m}{2m_e r \sin\theta} |\psi_{nlm}|^2 = \frac{\hbar m}{m_e r \sin\theta} |\psi_{nlm}|^2$。

电流是围绕 $z$ 轴的许多环形电流（在 $x$-$y$ 平面），$d\vec{\mu} = dI \times \vec{S}$。

环形电流元：$dI = j_\varphi \times (r d\theta) \times dr$，截面面积 $(r d\theta) \times dr$，电流 $= j_\varphi \times r d\theta \, dr$。

磁矩元：$d\mu = dI \times \pi (r \sin\theta)^2 = j_\varphi \times r d\theta \, dr \times \pi r^2 \sin^2\theta$。

## 碱金属原子

碱金属原子的势能为：

$$V(r)=-\frac{ke^2}{r}$$

（氢原子）$V(r)=-\frac{e^2}{r}$，$a_0=$（玻尔半径）。

径向方程为：

$$\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right)+\frac{2\mu}{\hbar^2}\left(E+\frac{ke^2}{r}\right)-\frac{l(l+1)}{r^2}\right]R_l(r)=0$$

$$\left[\frac{d^2}{dr^2}+\frac{2}{r}\frac{d}{dr}+\frac{2\mu}{\hbar^2}\left(E+\frac{ke^2}{r}\right)-\frac{l(l+1)}{r^2}\right]R(r)=0$$

令 $l(l+1)-2\lambda=l'(l'+1)$，则类比氢原子：

$$E_n=-\frac{\mu k^2 e^4}{2\hbar^2 n^2},\qquad n=n_r+l'+1$$

$$l'=-\frac{1}{2}+\sqrt{\left(l+\frac{1}{2}\right)^2-2\lambda}=-\left(l+\frac{1}{2}\right)+\sqrt{\left(l+\frac{1}{2}\right)^2-2\lambda}$$

$l'$ 与 $\lambda$ 有关，能级简并度为 $2l'+1$。

## 电磁场中电荷粒子的哈密顿量

在电磁场中，存在带电量为 $q$，质量为 $m$ 的粒子，粒子受力：

$$\mathbf{F}=q\mathbf{E}+q\mathbf{v}\times\mathbf{B}$$

由 $\nabla\cdot\mathbf{B}=0$，则引入 $\mathbf{A}$ 为矢势：

$$\mathbf{B}=\nabla\times\mathbf{A},\qquad \mathbf{E}=-\nabla\phi-\frac{\partial\mathbf{A}}{\partial t}$$

（$\nabla\cdot\mathbf{B}=0$，$\nabla\times\mathbf{E}=-\frac{\partial\mathbf{B}}{\partial t}$）$\phi$ 为电势。

$$\mathbf{A}=(A_x,\ A_y,\ A_z)$$

$$\nabla\times\mathbf{B}=\nabla\times(\nabla\times\mathbf{A})=\nabla(\nabla\cdot\mathbf{A})-\nabla^2\mathbf{A}$$

$$\mathbf{B}=(B_x,\ B_y,\ B_z)$$

$$F_x=q\left[-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+v_y\left(\frac{\partial A_y}{\partial x}-\frac{\partial A_x}{\partial y}\right)-v_z\left(\frac{\partial A_x}{\partial z}-\frac{\partial A_z}{\partial x}\right)\right]$$

考虑 $A_x(x,y,z,t)$，则：

$$\frac{dA_x}{dt}=\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}$$

故：

$$F_x=q\left[-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}\right]=-q\frac{\partial\phi}{\partial x}-q\frac{dA_x}{dt}+q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})$$

由 $\mathbf{F}=\frac{d}{dt}(m\mathbf{v})$，则：

$$\frac{d}{dt}(m\dot{x}+qA_x)=q\left(-\frac{\partial\phi}{\partial x}\right)+q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})$$

令 $U=q(\phi-\mathbf{A}\cdot\mathbf{v})$，则：

$$\frac{\partial U}{\partial x}=q\frac{\partial\phi}{\partial x}-q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})=-q\frac{\partial\phi}{\partial x}+q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})$$

$$\frac{\partial U}{\partial \dot{x}}=-qA_x,\qquad \frac{\partial U}{\partial \dot{y}}=-qA_y,\qquad \frac{\partial U}{\partial \dot{z}}=-qA_z$$

由拉格朗日方程：

$$\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{x}}\right)-\frac{\partial L}{\partial x}=F_x=-q\frac{\partial}{\partial x}(\phi-\mathbf{A}\cdot\mathbf{v})$$

$$T=\frac{1}{2}m\dot{x}^2$$

$$\frac{d}{dt}\left(\frac{\partial}{\partial \dot{x}}(T+q\phi-q\mathbf{A}\cdot\mathbf{v})\right)-\frac{\partial}{\partial x}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})=0$$

$$\frac{d}{dt}\left(\frac{\partial}{\partial \dot{x}}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})\right)-\frac{\partial}{\partial x}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})=0$$

$y$、$z$ 方向同理。

$$\frac{\partial L}{\partial \dot{x}}=m\dot{x}+qA_x$$

## 哈密顿量

$$H = -L = (mv + qA) \cdot v - \frac{1}{2}mv^2 - (-V \cdot A) = \frac{1}{2}mv^2 + q = \frac{1}{2m}(P - qA)^2 + q\varphi$$

考虑系统中心力，$V = \frac{1}{2}m\omega^2 r^2 + 0 + \cdots$

## 补充：坐标系变换

### ① 典型空间中的度规

**二维空间**，线元 $ds^2 = (dx)^2 + (dy)^2 = (dx, dy) \begin{pmatrix} dx \\ dy \end{pmatrix} = g_{ij} dx^i dx^j$

若取极坐标系 $r, \varphi$，$x = r\cos\varphi$，$y = r\sin\varphi$，则

$$ds^2 = (dr\cos\varphi - r\sin\varphi\, d\varphi)^2 + (dr\sin\varphi + r\cos\varphi\, d\varphi)^2 = dr^2 + (r\, d\varphi)^2$$

$$ds^2 = g_{ij} dx^i dx^j, \quad G = \begin{pmatrix} 1 & 0 \\ 0 & r^2 \end{pmatrix}$$

**三维欧氏空间**，线元 $ds^2 = (dx)^2 + (dy)^2 + (dz)^2 = \sum_{ij} \delta_{ij} dx^i dx^j$，$\delta = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$

若取球坐标，即 $\{x^1, x^2, x^3\} = \{r, \theta, \varphi\}$，$x = r\sin\theta\cos\varphi$，$y = r\sin\theta\sin\varphi$，$z = r\cos\theta$，则

$$G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2\sin^2\theta \end{pmatrix}$$

### 梯度算子

$h_i = \sqrt{(\frac{\partial x}{\partial q^i})^2 + (\frac{\partial y}{\partial q^i})^2 + (\frac{\partial z}{\partial q^i})^2}$，在 $q^2, q^3$ 不变而 $q^1$ 相差微小变量时，线元 $(ds)^2 = h_1^2 (dq^1)^2$（正交曲线坐标）。

对标量函数 $u(q^1, q^2, q^3)$，在增长方向的梯度 $(\nabla u)_i = \frac{1}{h_i} \frac{\partial u}{\partial q^i} \mathbf{e}_i$

#### 笛卡尔坐标系中的表示

事实上，考虑 $\nabla u = \frac{\partial u}{\partial x} \mathbf{e}_x + \frac{\partial u}{\partial y} \mathbf{e}_y + \frac{\partial u}{\partial z} \mathbf{e}_z$

于是有 $\left(\frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z}\right) = \left(\frac{\partial u}{\partial q^1}, \frac{\partial u}{\partial q^2}, \frac{\partial u}{\partial q^3}\right) \frac{\partial(q^1, q^2, q^3)}{\partial(x, y, z)}$

又 $\left(\frac{\partial u}{\partial q^1}, \frac{\partial u}{\partial q^2}, \frac{\partial u}{\partial q^3}\right) = \left(\frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z}\right) \frac{\partial(x, y, z)}{\partial(q^1, q^2, q^3)}$

即

### 角向方程

角向方程可写为：

\[
\sin\theta \frac{\partial}{\partial\theta}\left(\sin\theta \frac{\partial \Theta}{\partial\theta}\right) + \left[ l(l+1)\sin^2\theta - m^2 \right]\Theta = 0
\]

其解为连带勒让德函数 \(P_l^m(\cos\theta)\)，与方位角部分 \(e^{im\phi}\) 结合构成球谐函数 \(Y_l^m(\theta,\phi)\)。

$$\frac{\partial(u, v, w)}{\partial(x, y, z)} = \frac{\partial(u, v, w)}{\partial(q^1, q^2, q^3)} \cdot \frac{\partial(q^1, q^2, q^3)}{\partial(x, y, z)}$$

$$\frac{\partial(x, y, z)}{\partial(u, v, w)} = \frac{\partial(x, y, z)}{\partial(q^1, q^2, q^3)} \cdot \frac{\partial(q^1, q^2, q^3)}{\partial(u, v, w)}$$

$$\left(\frac{\partial x}{\partial u}\right)_{v,w} = \frac{\partial(x, y, z)}{\partial(u, v, w)} \cdot \frac{\partial(u, v, w)}{\partial(x, y, z)} = 1$$

## 散度向量场在闭合曲面的通量等于向量场的散度在曲面包围区域的体积分

设向量场 $\mathbf{a}$，闭合曲面 $S$ 包围区域 $V$，则：

$$\oint_S \mathbf{a} \cdot d\mathbf{S} = \iiint_V \nabla \cdot \mathbf{a} \, dV$$

在曲线坐标 $(u, v, w)$ 中，考虑平行于 $d$ 的四个面，在剩下两面中一个面的通量为：

两个面的通量之差为 $\left( \frac{\partial}{\partial u} J \right) du \, dv \, dw = \frac{\partial}{\partial u} (J a_u) \, du \, dv \, dw$

同理，另外两个通量差为 $\frac{\partial}{\partial v} (J a_v) \, du \, dv \, dw$，$\frac{\partial}{\partial w} (J a_w) \, du \, dv \, dw$

$$\therefore (\nabla \cdot \mathbf{a}) V = (\nabla \cdot \mathbf{a}) J \, du \, dv \, dw = \left[ \frac{\partial}{\partial u} (J a_u) + \frac{\partial}{\partial v} (J a_v) + \frac{\partial}{\partial w} (J a_w) \right] du \, dv \, dw$$

$$\nabla \cdot \mathbf{a} = \frac{1}{J} \left[ \frac{\partial}{\partial u} (J a_u) + \frac{\partial}{\partial v} (J a_v) + \frac{\partial}{\partial w} (J a_w) \right] = \frac{1}{H_u H_v H_w} \left[ \frac{\partial}{\partial u} (H_v H_w a_u) + \frac{\partial}{\partial v} (H_u H_w a_v) + \frac{\partial}{\partial w} (H_u H_v a_w) \right]$$

如 $(u, v, w) = (r, \theta, \varphi)$，则：

$$\nabla \cdot \mathbf{F} = \frac{1}{r^2 \sin \theta} \left[ \frac{\partial}{\partial r} (r^2 \sin \theta \, F_r) + \frac{\partial}{\partial \theta} (\sin \theta \, F_\theta) + \frac{\partial}{\partial \varphi} (r F_\varphi) \right] = \frac{1}{r^2} \frac{\partial}{\partial r} (r^2 F_r) + \frac{1}{r \sin \theta} \frac{\partial}{\partial \theta} (\sin \theta \, F_\theta) + \frac{1}{r \sin \theta} \frac{\partial F_\varphi}{\partial \varphi}$$

## 旋度

$$\text{rot} \, \mathbf{a} = \lim_{S \to 0} \frac{\oint_S \mathbf{a} \cdot d\mathbf{S}}{S} = \nabla \times \mathbf{a}$$

考虑 $\text{rot} \, \mathbf{a}$ 在 $u$ 轴上的投影，取 $\mathbf{n}$ 为正方向，$S$ 面是 $u = \text{常数}$，曲面 $S$ 中的曲线 $L$ 设为 $M_1 M_2 N_2 N_1$。

$$\int_{M_1 M_2} \mathbf{a} \cdot d\mathbf{l} = \mathbf{a}(u, v, w) \cdot d\mathbf{l} = a_v (u, v, w) H_v (u, v, w) \, dv$$

其中 $M_1 = (u, v, w)$，$M_2 = (u, v + dv, w)$，$N_1 = (u, v, w + dw)$，$N_2 = (u, v + dv, w + dw)$。

$$\int_{M_2 N_2} \mathbf{a} \cdot d\mathbf{l} = \mathbf{a}(u, v + dv, w) \cdot d\mathbf{l} = a_w (u, v + dv, w) H_w (u, v + dv, w) \, dw$$

$$\int_{N_2 N_1} \mathbf{a} \cdot d\mathbf{l} = \mathbf{a}(u, v, w + dw) \cdot d\mathbf{l} = -a_v (u, v, w + dw) H_v (u, v, w + dw) \, dv$$

$$\int_{N_1 M_1} \mathbf{a} \cdot d\mathbf{l} = -\mathbf{a}(u, v, w) \cdot d\mathbf{l} = -a_w (u, v, w) H_w (u, v, w) \, dw$$

则环量为：

$$\oint \mathbf{a} \cdot d\mathbf{l} = \left[ \frac{\partial (a_w H_w)}{\partial v} - \frac{\partial (a_v H_v)}{\partial w} \right] dv \, dw = (\text{rot} \, \mathbf{a})_u \, dv \, dw = \frac{1}{H_v H_w} \left[ \frac{\partial (a_w H_w)}{\partial v} - \frac{\partial (a_v H_v)}{\partial w} \right] H_u H_v H_w \, dv \, dw$$

$$(\text{rot} \, \mathbf{a})_u = \frac{1}{H_v H_w} \left[ \frac{\partial (a_w H_w)}{\partial v} - \frac{\partial (a_v H_v)}{\partial w} \right]$$

SMm₂a.d3=a(u，Vv，w）·d=a(uv，）·H·d=av(V.w）Hv(u,V，w）dv
∫M₂N₂a.d3=a(u，v+dv，w）d=a(uv+dv，ω)Hdω=a（uV+dV，W）Hw（uV+dv，w）dw
SN₂N₁ad=a(u，V，W+dw）)d=-a(u，w+dw）Hdve=-a(u，W+dw）Huv，w+d）dv
∫N，M₁a.d=-a(uv，ω）Hwdwe=-a(u，W)Hw（u,V，wd.
则a.d^3{=3(a =(22a1)翻 re ∂uHw me dvdw mHH (H^D)e ou ∂(avHw) me (rot ā)w dvdw= = d(awHω) ∂av ∂u ne ^HnH$ α(uHu 7e ∂(avH me dv dw(rot a)_= 0(awHw) ∂ mH^H $α(a{}_v}$ ∂ω
$rot a=$\fr$ 3a $\fra}}$