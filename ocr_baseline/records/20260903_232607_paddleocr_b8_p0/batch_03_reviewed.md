# 氢原子与碱金属原子

## 概率密度与角度分布

概率密度角度分布在 $(\theta, \varphi)$ 方向的立体角 $d\Omega$ 中电子的概率为 $|Y_{lm}(\theta, \varphi)|^2 d\Omega = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$。

关于径向概率分布：$P = r^2 \sin\theta \, dr \, d\theta \, d\varphi$。

关于概率密度角度分布：$P(\theta, \theta+d\theta; \varphi, \varphi+d\varphi) = \int |R_{nl}|^2 r^2 \sin\theta \, dr \, d\theta \, d\varphi = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$。

## 电流分布与磁矩

电流密度 = 电荷 × 概率流密度：

$$\vec{j}_c = (-e) \cdot \frac{\hbar}{2\mu i} (\psi^* \nabla \psi - \psi \nabla \psi^*)$$

其中 $\psi_{nlm}(r, \theta, \varphi) = NR_{nl}(r) P_l^m(\cos\theta) e^{im\varphi}$，$R_{nl}(r)$ 为实函数，则 $j_r = 0$。

$$j_\varphi = \frac{e\hbar m}{\mu r \sin\theta} |\psi|^2$$

$\vec{j}$ 是围绕 $z$ 轴的许多环形电流（在 $x$-$y$ 平面），$d\vec{\mu} = dI \times \vec{S}$。

环形电流元：$dI = j_\varphi \times r \, d\theta \, dr$，截面面积：$(r\, d\theta) \times dr$。

磁矩：$d\mu = \pi (r\sin\theta)^2 \times dI$。

# 碱金属原子

势能：氢原子 $V(r) = -\frac{e^2}{r}$，碱金属原子 $V(r) = -\frac{e^2}{r} - \frac{\lambda e^2}{r^2}$，其中 $a_0 = \frac{\hbar^2}{\mu e^2}$。

径向方程：

$$\left[ \frac{1}{r^2} \frac{d}{dr} \left( r^2 \frac{d}{dr} \right) + \frac{2\mu}{\hbar^2} \left( E + \frac{e^2}{r} + \frac{\lambda e^2}{r^2} \right) - \frac{l(l+1)}{r^2} \right] R_{nl}(r) = 0$$

令 $l'(l'+1) = l(l+1) - 2\lambda$，则类比氢原子：

$$E_n = -\frac{\mu e^4}{2\hbar^2 n'^2}, \quad n' = n_r + l' + 1$$

$$l' = -\frac{1}{2} + \sqrt{\left(l + \frac{1}{2}\right)^2 - 2\lambda} = -\frac{1}{2} + \left(l + \frac{1}{2}\right) \sqrt{1 - \frac{2\lambda}{\left(l + \frac{1}{2}\right)^2}}$$

$l'$ 与 $l$ 有关，能级简并度为 $2l+1$。

# 电磁场中电荷粒子的哈密顿量

在电磁场中，存在带电量为 $q$，质量为 $m$ 的粒子，粒子受力 $\vec{F} = q\vec{E} + q\vec{v} \times \vec{B}$。

由 $\nabla \cdot \vec{B} = 0$，则引入 $\vec{A}$ 为矢势，$\vec{B} = \nabla \times \vec{A}$，$\vec{E} = -\nabla \varphi - \frac{\partial \vec{A}}{\partial t}$（$\varphi$ 为电势）。

由 $\nabla \times \vec{B} = \mu_0 \vec{j}$，分量形式：

$$F_x = q\left[ -\frac{\partial \varphi}{\partial x} - \frac{\partial A_x}{\partial t} + v_y \left( \frac{\partial A_y}{\partial x} - \frac{\partial A_x}{\partial y} \right) - v_z \left( \frac{\partial A_x}{\partial z} - \frac{\partial A_z}{\partial x} \right) \right]$$

考虑 $A_x(x, y, z, t)$，则 $\frac{dA_x}{dt} = \frac{\partial A_x}{\partial t} + v_x \frac{\partial A_x}{\partial x} + v_y \frac{\partial A_x}{\partial y} + v_z \frac{\partial A_x}{\partial z}$。

故：

$$F_x = q\left[ -\frac{\partial \varphi}{\partial x} - \frac{dA_x}{dt} + \frac{\partial}{\partial x}(\vec{v} \cdot \vec{A}) \right] = q\left[ -\frac{\partial \varphi}{\partial x} - \frac{dA_x}{dt} + \frac{\partial}{\partial x}(\vec{v} \cdot \vec{A}) \right]$$

由 $\frac{d}{dt}(m\vec{v}) = \vec{F}$，则 $\frac{d}{dt}(m v_x + q A_x) = q\left( -\frac{\partial \varphi}{\partial x} \right) + q \frac{\partial}{\partial x}(\vec{v} \cdot \vec{A})$。

令 $U = q(\varphi - \vec{A} \cdot \vec{v})$，则 $\frac{\partial U}{\partial x} = q\left( \frac{\partial \varphi}{\partial x} - \frac{\partial}{\partial x}(\vec{A} \cdot \vec{v}) \right)$，$\frac{\partial U}{\partial v_x} = -q A_x$，$\frac{\partial U}{\partial v_y} = -q A_y$，$\frac{\partial U}{\partial v_z} = -q A_z$。

由拉格朗日方程：$\frac{d}{dt}\left( \frac{\partial L}{\partial \dot{x}} \right) - \frac{\partial L}{\partial x} = F_x = -q \frac{\partial}{\partial x}(\varphi - \vec{A} \cdot \vec{v})$，$T = \frac{1}{2} m v^2$。

$$\frac{d}{dt}(m\dot{x} + qA_x) - \frac{\partial}{\partial x}(T - q\varphi + q\vec{A} \cdot \vec{v}) = 0$$

即 $\frac{d}{dt}(m\dot{x} + qA_x) - \frac{\partial}{\partial x}(T - q\varphi + q\vec{A} \cdot \vec{v}) = 0$，$y$、$z$ 同理。

哈密顿量：

$$H = \vec{v} \cdot \vec{p} - L = (m\vec{v} + q\vec{A}) \cdot \vec{v} - \left( \frac{1}{2} m v^2 - q\varphi + q\vec{A} \cdot \vec{v} \right) = \frac{1}{2} m v^2 + q\varphi = \frac{1}{2m}(\vec{p} - q\vec{A})^2 + q\varphi$$

考虑系统中心力场：$H = \frac{1}{2m} \vec{p}^2 - \frac{e^2}{r} + \cdots$。

# 补充：坐标系变换

同理，另外两个通量差为（)dudvdw，（dudvdw.

考虑rota在u轴上的投影，取n{为正方向，S面是u=常数，曲面S中的曲线L设为\$MM_{2}_{2}_₁

$N_}$ $N_{2}$ (u,V+aV,w+dω)

(91,82,93) \$(81._2+d_{292) (u,V，w)M M₂(u，V+dv，w)

简单塞曼效应

无外加电磁场时，A=²+V(n)，V(r）=-k²-λk1²

简单塞曼效应

无外加电磁场时，\(\hat{H} = \frac{\hat{p}^2}{2\mu} + V(r)\)，其中 \(V(r) = -\frac{k}{r} - \frac{\lambda}{r^2}\)。

分离变量后，径向方程为：

\[
\left[ -\frac{\hbar^2}{2\mu} \frac{1}{r^2} \frac{d}{dr} \left( r^2 \frac{d}{dr} \right) + \frac{\hbar^2 l(l+1)}{2\mu r^2} + V(r) - E \right] R(r) = 0
\]

令 \(R(r) = \frac{u(r)}{r}\)，则方程化为：

\[
-\frac{\hbar^2}{2\mu} \frac{d^2 u}{dr^2} + \left[ \frac{\hbar^2 l(l+1)}{2\mu r^2} + V(r) \right] u(r) = E u(r)
\]

对比碱金属原子方程，有 \(E_0 = -\frac{\mu k^2}{2\hbar^2}\)，且 \(l\) 的有效值需修正。

当 \(B=0\) 时，能级简并度为 \(2l+1\)，即一个能级对应 \(2l+1\) 个量子态。

## 典型空间中的度规

二维空间，线元 $ds^2 = (dx)^2 + (dy)^2 = (dx, dy) \begin{pmatrix} dx \\ dy \end{pmatrix} = g_{ij} dx^i dx^j$。

若取极坐标系 $r, \varphi$，$x = r\cos\varphi$，$y = r\sin\varphi$，则：

$$ds^2 = (dr\cos\varphi - r\sin\varphi \, d\varphi)^2 + (dr\sin\varphi + r\cos\varphi \, d\varphi)^2 = dr^2 + r^2 (d\varphi)^2$$

$$ds^2 = g_{ij} dx^i dx^j, \quad G = \begin{pmatrix} 1 & 0 \\ 0 & r^2 \end{pmatrix}$$

三维欧氏空间，线元 $ds^2 = (dx)^2 + (dy)^2 + (dz)^2 = g_{ij} dx^i dx^j$，$g_{ij} = \delta_{ij}$。

若取球坐标，即 $\{x^1, x^2, x^3\} = \{r, \theta, \varphi\}$，$x = r\sin\theta\cos\varphi$，$y = r\sin\theta\sin\varphi$，$z = r\cos\theta$。

$$G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2 \sin^2\theta \end{pmatrix}$$

## 梯度算子

$h_i = \sqrt{g_{ii}}$，在 $q_2, q_3$ 不变而 $q_1$ 相差微小变量时，线元 $(ds)^2 = h_1^2 (dq_1)^2$（正交坐标系）。

对标量函数 $u(q_1, q_2, q_3)$，在 $u$ 增长方向的梯度 $(\nabla u)_i = \frac{1}{h_i} \frac{\partial u}{\partial q_i} \vec{e}_i$。

### 笛卡尔坐标系中的表示

事实上，考虑 $\nabla u = \frac{\partial u}{\partial x} \vec{e}_x + \frac{\partial u}{\partial y} \vec{e}_y + \frac{\partial u}{\partial z} \vec{e}_z$。

于是有 $\left( \frac{\partial u}{\partial q_1}, \frac{\partial u}{\partial q_2}, \frac{\partial u}{\partial q_3} \right) = \left( \frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z} \right) \frac{\partial(x, y, z)}{\partial(q_1, q_2, q_3)}$。

即：

$$\frac{\partial(u, v, w)}{\partial(x, y, z)} = \frac{\partial(u, v, w)}{\partial(q_1, q_2, q_3)} \cdot \frac{\partial(q_1, q_2, q_3)}{\partial(x, y, z)}$$

$$\nabla u = \frac{1}{h_1} \frac{\partial u}{\partial q_1} \vec{e}_1 + \frac{1}{h_2} \frac{\partial u}{\partial q_2} \vec{e}_2 + \frac{1}{h_3} \frac{\partial u}{\partial q_3} \vec{e}_3$$

## 散度

向量场在闭合曲面的通量等于向量场的散度在曲面包围区域的体积分。

$$\oint_S \vec{a} \cdot d\vec{S} = \int_V \nabla \cdot \vec{a} \, dV$$

考虑平行于 $d\vec{S}$ 的四个面，在剩下两面中一个面的通量为：

$$(a_u H_v H_w)(u, v, w) \, dv \, dw$$

两个面的通量之差为 $\frac{\partial}{\partial u}(a_u H_v H_w) \, du \, dv \, dw$。

同理，另外两个通量差为 $\frac{\partial}{\partial v}(a_v H_w H_u) \, du \, dv \, dw$，$\frac{\partial}{\partial w}(a_w H_u H_v) \, du \, dv \, dw$。

$$\therefore (\nabla \cdot \vec{F}) \, dV = (\nabla \cdot \vec{F}) |J| \, du \, dv \, dw = \left[ \frac{\partial}{\partial u}(a_u H_v H_w) + \frac{\partial}{\partial v}(a_v H_w H_u) + \frac{\partial}{\partial w}(a_w H_u H_v) \right] du \, dv \, dw$$

$$\nabla \cdot \vec{F} = \frac{1}{H_u H_v H_w} \left[ \frac{\partial}{\partial u}(a_u H_v H_w) + \frac{\partial}{\partial v}(a_v H_w H_u) + \frac{\partial}{\partial w}(a_w H_u H_v) \right]$$

如 $(u, v, w) = (r, \theta, \varphi)$，则：

$$\nabla \cdot \vec{F} = \frac{1}{r^2 \sin\theta} \left[ \frac{\partial}{\partial r}(r^2 \sin\theta \, F_r) + \frac{\partial}{\partial \theta}(\sin\theta \, F_\theta) + \frac{\partial}{\partial \varphi}(r F_\varphi) \right] = \frac{1}{r^2} \frac{\partial}{\partial r}(r^2 F_r) + \frac{1}{r\sin\theta} \frac{\partial}{\partial \theta}(\sin\theta \, F_\theta) + \frac{1}{r\sin\theta} \frac{\partial F_\varphi}{\partial \varphi}$$

## 旋度

$$\text{rot} \, \vec{a} = \lim_{S \to 0} \frac{\oint \vec{a} \cdot d\vec{l}}{S}$$

考虑 $\text{rot} \, \vec{a}$ 在 $u$ 轴上的投影，取 $\vec{n}$ 为正方向，$S$ 面是 $u$ = 常数，曲面 $S$ 中的曲线 $L$ 设为 $M_1 M_2 N_2 N_1$。

$$\int_{M_1 M_2} \vec{a} \cdot d\vec{l} = a(u, v, w) \cdot H_v \, dv = a_v(u, v, w) H_v(u, v, w) \, dv$$

$$\int_{M_2 N_2} \vec{a} \cdot d\vec{l} = a(u, v+dv, w) \cdot H_w \, dw = a_w(u, v+dv, w) H_w(u, v+dv, w) \, dw$$

$$\int_{N_2 N_1} \vec{a} \cdot d\vec{l} = -a(u, v, w+dw) \cdot H_v \, dv = -a_v(u, v, w+dw) H_v(u, v, w+dw) \, dv$$

$$\int_{N_1 M_1} \vec{a} \cdot d\vec{l} = -a(u, v, w) \cdot H_w \, dw = -a_w(u, v, w) H_w(u, v, w) \, dw$$

则：

$$\oint \vec{a} \cdot d\vec{l} = \left[ \frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v) \right] dv \, dw$$

$$(\text{rot} \, \vec{a})_u = \frac{1}{H_v H_w} \left[ \frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v) \right]$$

$$\text{rot} \, \vec{a} = \frac{1}{H_u H_v H_w} \begin{vmatrix} H_u \vec{e}_u & H_v \vec{e}_v & H_w \vec{e}_w \\ \frac{\partial}{\partial u} & \frac{\partial}{\partial v} & \frac{\partial}{\partial w} \\ H_u a_u & H_v a_v & H_w a_w \end{vmatrix}$$

# 简单塞曼效应

无外加电磁场时，$H = \frac{p^2}{2\mu} + V(r)$，$V(r) = -\frac{e^2}{r} - \frac{\lambda e^2}{r^2}$。

加入磁场 $\vec{B} = B \vec{e}_z$，$H' = H + H^{(1)}$（后证）。

电荷为 $q$，质量为 $\mu$ 的粒子在矢势 $\vec{A}$ 和标势 $\varphi$ 中，有：

$$H = \frac{(\vec{p} - q\vec{A})^2}{2\mu} + V + q\varphi$$

选 $\vec{A} = \frac{1}{2}(-y, x, 0) B$，则：

$$H = \frac{1}{2\mu} \left[ \left( p_x + \frac{qBy}{2} \right)^2 + \left( p_y - \frac{qBx}{2} \right)^2 + p_z^2 \right] + V(r)$$

$$= \frac{p^2}{2\mu} + \frac{qB}{2\mu}(x p_y - y p_x) + \frac{q^2 B^2}{8\mu}(x^2 + y^2) + V(r)$$

其中 $L_z = x p_y - y p_x$，$\rho^2 = x^2 + y^2$。

$$H \psi_{nlm} = E_{nlm} \psi_{nlm}, \quad \psi_{nlm}(r, \theta, \varphi) = R_{nl}(r) Y_{lm}(\theta, \varphi)$$

则：

$$\left[ -\frac{\hbar^2}{2\mu} \nabla^2 + V(r) + \frac{qB}{2\mu} L_z + \frac{q^2 B^2}{8\mu} \rho^2 \right] R_{nl}(r) Y_{lm}(\theta, \varphi) = E R_{nl}(r) Y_{lm}(\theta, \varphi)$$

于是有：

$$\left[ -\frac{\hbar^2}{2\mu} \frac{1}{r^2} \frac{d}{dr} \left( r^2 \frac{d}{dr} \right) + \frac{l(l+1)\hbar^2}{2\mu r^2} + V(r) + \frac{qB}{2\mu} m\hbar + \frac{q^2 B^2}{8\mu} r^2 \sin^2\theta \right] R_{nl}(r) Y_{lm}(\theta, \varphi) = E R_{nl}(r) Y_{lm}(\theta, \varphi)$$

**注意**：左式 $= \left[ -\frac{\hbar^2}{2\mu r^2} \frac{d}{dr} \left( r^2 \frac{d}{dr} \right) + \frac{l(l+1)\hbar^2}{2\mu r^2} + V(r) \right] R_{nl}(r) Y_{lm}(\theta, \varphi) + \frac{qB}{2\mu} m\hbar R_{nl}(r) Y_{lm}(\theta, \varphi) + \frac{q^2 B^2}{8\mu} r^2 \sin^2\theta \, R_{nl}(r) Y_{lm}(\theta, \varphi) = E R_{nl}(r) Y_{lm}(\theta, \varphi)$

令 $E_0 = E - \omega_L m\hbar = E - m\hbar \omega_L$，代入 $V(r) = -\frac{e^2}{r} - \frac{\lambda e^2}{r^2}$：

则 $\left[ -\frac{\hbar^2}{2\mu r^2} \frac{d}{dr} \left( r^2 \frac{d}{dr} \right) + \frac{l(l+1)\hbar^2}{2\mu r^2} - \frac{e^2}{r} - \frac{\lambda e^2}{r^2} - (\omega_L m\hbar - E) \right] R_{nl}(r) = 0$

$$\left[ -\frac{\hbar^2}{2\mu} \frac{d^2}{dr^2} + \frac{l(l+1)\hbar^2}{2\mu r^2} - \frac{e^2}{r} - \frac{\lambda e^2}{r^2} + E_0 \right] R(r) = 0$$

对比碱金属原子方程，有 $E_0 = -\frac{\mu e^4}{2\hbar^2 n'^2}$，$E = E_0 + m\hbar \omega_L$。

**$B = 0$ 时**，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。

**$B \neq 0$ 时**，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，不简并。

Huau $H_v}_v}$ Hwaw
单中科技

$B_{}By B_$ +[x(-）-

0 0 0 D 0 $r^{2}smθ 0 0

Huē $H_v}_}$ HwEw