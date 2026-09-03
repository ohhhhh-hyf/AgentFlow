# 氢原子与碱金属原子

## 概率密度与角度分布

概率密度角度分布在 $(\theta, \varphi)$ 方向的立体角 $d\Omega$ 中电子的概率为 $|Y_{lm}(\theta, \varphi)|^2 d\Omega = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$。

关于径向概率分布：$P = r^2 \sin\theta \, dr \, d\theta \, d\varphi$。

关于概率密度角度分布：$P(\theta, \theta+d\theta; \varphi, \varphi+d\varphi) = \int |R_{nl}|^2 r^2 \sin\theta \, dr \, d\theta \, d\varphi = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$。

## 电流分布与磁矩

电流密度 = 电荷 × 概率流密度：

$$\vec{j}_c = (-e) \cdot \frac{\hbar}{2\mu i} (\psi^* \nabla \psi - \psi \nabla \psi^*)$$

其中 $\psi_{nlm}(r, \theta, \varphi) = NR_{nl}(r) P_l^m(\cos\theta) e^{im\varphi}$，$R_{nl}(r)$ 为实函数，则 $j_r = 0$，$j_\theta = 0$。

$$j_\varphi = \frac{e\hbar m}{\mu r \sin\theta} |\psi_{nlm}|^2$$

电流围绕 $z$ 轴形成许多环形电流（在 $x$-$y$ 平面），$d\vec{I} = \vec{j} \, dS$。

环形电流的截面积：$(r d\theta) \times dr$，电流 $dI = j_\varphi \times r \, d\theta \, dr$。

磁矩 $d\vec{\mu} = dI \times \vec{S}$，其中 $S = \pi (r\sin\theta)^2$。

# 碱金属原子

碱金属原子的势能：

$$V(r) = -\frac{e^2}{r} \quad (\text{氢原子}), \qquad V(r) = -\frac{e^2}{r} - \frac{\lambda e^2}{r^2} \quad (\text{碱金属原子})$$

其中 $a_0 = \frac{\hbar^2}{\mu e^2}$。

径向方程：

$$\frac{1}{r^2} \frac{d}{dr} \left( r^2 \frac{dR}{dr} \right) + \frac{2\mu}{\hbar^2} \left( E + \frac{e^2}{r} + \frac{\lambda e^2}{r^2} \right) R(r) = 0$$

令 $l(l+1) - 2\lambda = l'(l'+1)$，则类比氢原子：

$$E_n = -\frac{\mu e^4}{2\hbar^2 n'^2}, \qquad n' = n_r + l' + 1$$

$$l' = -\frac{1}{2} + \sqrt{\left(l + \frac{1}{2}\right)^2 - 2\lambda} = -\frac{1}{2} + \left(l + \frac{1}{2}\right) \sqrt{1 - \frac{2\lambda}{\left(l + \frac{1}{2}\right)^2}}$$

$l'$ 与 $l$ 有关，能级简并度为 $2l+1$。

# 电磁场中电荷粒子的哈密顿量

在电磁场中，存在带电量为 $q$，质量为 $m$ 的粒子，粒子受力：

$$\vec{F} = q\vec{E} + q\vec{v} \times \vec{B}$$

由 $\nabla \cdot \vec{B} = 0$，引入 $\vec{A}$ 为矢势，$\vec{B} = \nabla \times \vec{A}$，$\vec{E} = -\nabla \varphi - \frac{\partial \vec{A}}{\partial t}$（$\varphi$ 为电势）。

$$\nabla \times \vec{B} = \nabla \times (\nabla \times \vec{A}) = \nabla(\nabla \cdot \vec{A}) - \nabla^2 \vec{A}$$

考虑 $A_x(x, y, z, t)$，则 $\frac{dA_x}{dt} = \frac{\partial A_x}{\partial t} + \frac{\partial A_x}{\partial x} \dot{x} + \frac{\partial A_x}{\partial y} \dot{y} + \frac{\partial A_x}{\partial z} \dot{z}$。

由牛顿第二定律 $F_x = m\ddot{x}$，可得：

$$\frac{d}{dt}(m\dot{x} + qA_x) = q\left(-\frac{\partial \varphi}{\partial x} - \frac{\partial A_x}{\partial t}\right) + q\dot{x}\frac{\partial A_x}{\partial x} + q\dot{y}\frac{\partial A_y}{\partial x} + q\dot{z}\frac{\partial A_z}{\partial x}$$

令 $U = q(\varphi - \vec{A} \cdot \vec{v})$，则 $\frac{\partial U}{\partial x} = q\frac{\partial \varphi}{\partial x} - q\vec{v} \cdot \frac{\partial \vec{A}}{\partial x}$，$\frac{\partial U}{\partial \dot{x}} = -qA_x$，$\frac{\partial U}{\partial \dot{y}} = -qA_y$，$\frac{\partial U}{\partial \dot{z}} = -qA_z$。

由拉格朗日方程 $\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{x}}\right) - \frac{\partial L}{\partial x} = 0$，其中 $T = \frac{1}{2}mv^2$：

$$\frac{d}{dt}(m\dot{x} + qA_x) - \frac{\partial}{\partial x}(T - q\varphi + q\vec{A}\cdot\vec{v}) = 0$$

哈密顿量：

$$H = \vec{p} \cdot \vec{v} - L = (m\vec{v} + q\vec{A}) \cdot \vec{v} - \left( \frac{1}{2}mv^2 - q\varphi + q\vec{A}\cdot\vec{v} \right) = \frac{1}{2}mv^2 + q\varphi = \frac{1}{2m}(\vec{p} - q\vec{A})^2 + q\varphi$$

考虑系统中心力场：$H = \frac{1}{2m}\vec{p}^2 - \frac{e^2}{r} + \cdots$

# 补充：坐标系变换

## 典型空间中的度规

二维空间，线元 $ds^2 = (dx)^2 + (dy)^2 = (dx, dy) \begin{pmatrix} dx \\ dy \end{pmatrix} = g_{ij} dx^i dx^j$。

若取极坐标系 $(r, \varphi)$，$x = r\cos\varphi$，$y = r\sin\varphi$，则：

$$ds^2 = (dr\cos\varphi - r\sin\varphi \, d\varphi)^2 + (dr\sin\varphi + r\cos\varphi \, d\varphi)^2 = dr^2 + r^2 d\varphi^2$$

$$ds^2 = g_{ij} dx^i dx^j, \qquad G = \begin{pmatrix} 1 & 0 \\ 0 & r^2 \end{pmatrix}$$

三维欧氏空间，线元 $ds^2 = (dx)^2 + (dy)^2 + (dz)^2 = \delta_{ij} dx^i dx^j$，$\delta = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$。

若取球坐标 $\{x^1, x^2, x^3\} = \{r, \theta, \varphi\}$，$x = r\sin\theta\cos\varphi$，$y = r\sin\theta\sin\varphi$，$z = r\cos\theta$，则：

$$G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2\sin^2\theta \end{pmatrix}$$

## 梯度算子

$$h_i = \sqrt{\left(\frac{\partial x}{\partial q_i}\right)^2 + \left(\frac{\partial y}{\partial q_i}\right)^2 + \left(\frac{\partial z}{\partial q_i}\right)^2}$$

在 $q_2, q_3$ 不变而 $q_1$ 相差微小变量时，线元 $(ds)^2 = h_1^2 (dq_1)^2$（正交曲线坐标）。

对标量函数 $u(q_1, q_2, q_3)$，在 $u$ 增长方向的梯度 $(\nabla u)_i = \frac{1}{h_i}\frac{\partial u}{\partial q_i} \hat{e}_i$。

在笛卡尔坐标系中的表示：考虑 $\nabla u = \frac{\partial u}{\partial x}\hat{e}_x + \frac{\partial u}{\partial y}\hat{e}_y + \frac{\partial u}{\partial z}\hat{e}_z$。

由链式法则：

$$\frac{\partial u}{\partial q_i} = \frac{\partial u}{\partial x}\frac{\partial x}{\partial q_i} + \frac{\partial u}{\partial y}\frac{\partial y}{\partial q_i} + \frac{\partial u}{\partial z}\frac{\partial z}{\partial q_i}$$

即：

$$\begin{pmatrix} \frac{\partial u}{\partial q_1} \\ \frac{\partial u}{\partial q_2} \\ \frac{\partial u}{\partial q_3} \end{pmatrix} = \frac{\partial(u, v, w)}{\partial(x, y, z)} \begin{pmatrix} \frac{\partial u}{\partial x} \\ \frac{\partial u}{\partial y} \\ \frac{\partial u}{\partial z} \end{pmatrix}$$

其中 $\frac{\partial(u, v, w)}{\partial(x, y, z)}$ 为雅可比行列式。

## 散度

**向量场在闭合曲面的通量等于向量场的散度在曲面包围区域的体积分**（高斯定理）。

$$\oint_S \vec{a} \cdot d\vec{S} = \int_V \nabla \cdot \vec{a} \, dV$$

考虑平行于 $d\vec{u}$ 方向的四个面，在剩下两面中一个面的通量为 $a_u(u, v, w) H_v H_w \, dv \, dw$。

两个面的通量之差为 $\frac{\partial}{\partial u}(a_u H_v H_w) \, du \, dv \, dw$。

同理，另外两个方向通量差分别为 $\frac{\partial}{\partial v}(a_v H_w H_u) \, du \, dv \, dw$ 和 $\frac{\partial}{\partial w}(a_w H_u H_v) \, du \, dv \, dw$。

$$\therefore (\nabla \cdot \vec{F}) \, dV = \left[ \frac{\partial}{\partial u}(a_u H_v H_w) + \frac{\partial}{\partial v}(a_v H_w H_u) + \frac{\partial}{\partial w}(a_w H_u H_v) \right] du \, dv \, dw$$

$$\nabla \cdot \vec{F} = \frac{1}{H_u H_v H_w} \left[ \frac{\partial}{\partial u}(a_u H_v H_w) + \frac{\partial}{\partial v}(a_v H_w H_u) + \frac{\partial}{\partial w}(a_w H_u H_v) \right]$$

其中 $|J| = H_u H_v H_w$。

如 $(u, v, w) = (r, \theta, \varphi)$，则：

$$\nabla \cdot \vec{F} = \frac{1}{r^2 \sin\theta} \left[ \frac{\partial}{\partial r}(r^2 \sin\theta \, F_r) + \frac{\partial}{\partial \theta}(\sin\theta \, F_\theta) + \frac{\partial}{\partial \varphi}(r F_\varphi) \right] = \frac{1}{r^2}\frac{\partial}{\partial r}(r^2 F_r) + \frac{1}{r\sin\theta}\frac{\partial}{\partial \theta}(\sin\theta \, F_\theta) + \frac{1}{r\sin\theta}\frac{\partial F_\varphi}{\partial \varphi}$$

## 旋度

$$\text{rot} \, \vec{a} = \lim_{S \to 0} \frac{\oint_L \vec{a} \cdot d\vec{l}}{S}$$

考虑 $\text{rot} \, \vec{a}$ 在 $u$ 轴上的投影，取 $\hat{n}$ 为正方向，$S$ 面是 $u = \text{常数}$ 曲面，曲面 $S$ 中的曲线 $L$ 设为 $M_1 M_2 N_2 N_1$。

$$\int_{M_1 M_2} \vec{a} \cdot d\vec{l} = a_v(u, v, w) H_v(u, v, w) \, dv$$

$$\int_{M_2 N_2} \vec{a} \cdot d\vec{l} = a_w(u, v + dv, w) H_w(u, v + dv, w) \, dw$$

$$\int_{N_2 N_1} \vec{a} \cdot d\vec{l} = -a_v(u, v, w + dw) H_v(u, v, w + dw) \, dv$$

$$\int_{N_1 M_1} \vec{a} \cdot d\vec{l} = -a_w(u, v, w) H_w(u, v, w) \, dw$$

则：

$$\oint_L \vec{a} \cdot d\vec{l} = \left[ \frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v) \right] dv \, dw$$

$$(\text{rot} \, \vec{a})_u = \frac{1}{H_v H_w} \left[ \frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v) \right]$$

一般地：

$$\text{rot} \, \vec{a} = \frac{1}{H_u H_v H_w} \begin{vmatrix} H_u \hat{e}_u & H_v \hat{e}_v & H_w \hat{e}_w \\ \frac{\partial}{\partial u} & \frac{\partial}{\partial v} & \frac{\partial}{\partial w} \\ H_u a_u & H_v a_v & H_w a_w \end{vmatrix}$$

# 简单塞曼效应

无外加电磁场时，$H = \frac{\vec{p}^2}{2\mu} + V(r)$，$V(r) = -\frac{e^2}{r} - \frac{\lambda e^2}{r^2}$。

加入磁场 $\vec{B} = B \hat{e}_z$，$H' = H + H^{(1)}$（后证）。

电荷为 $q$，质量为 $\mu$ 的粒子在矢势 $\vec{A}$ 和标势 $\varphi$ 中：

$$H = \frac{(\vec{p} - q\vec{A})^2}{2\mu} + V + q\varphi$$

选 $\vec{A} = \frac{1}{2}(-y, x, 0)B$，则：

$$H = \frac{1}{2\mu}\left[ \left(p_x + \frac{qBy}{2}\right)^2 + \left(p_y - \frac{qBx}{2}\right)^2 + p_z^2 \right] + V(r)$$

$$= \frac{1}{2\mu}\left[ p_x^2 + p_y^2 + p_z^2 \right] + \frac{qB}{2\mu}(x p_y - y p_x) + \frac{q^2 B^2}{8\mu}(x^2 + y^2) + V(r)$$

其中 $L_z = x p_y - y p_x$，$\rho^2 = x^2 + y^2$。

本征方程：$H\psi_{nlm} = E_{nlm}\psi_{nlm}$，$\psi_{nlm}(r, \theta, \varphi) = R_{nl}(r) Y_{lm}(\theta, \varphi)$。

分离变量后得到径向方程和角向方程。

**注意**：左式 $= \frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right) - \frac{l(l+1)}{r^2}R + \frac{2\mu}{\hbar^2}\left(E - V(r)\right)R = 0$。

令 $E = E_0 + \omega_L m\hbar$，$E = E_0 + \omega_L m$，代入 $V(r) = -\frac{e^2}{r} - \frac{\lambda e^2}{r^2}$：

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right) + \frac{2\mu}{\hbar^2}\left( E_0 + \frac{e^2}{r} + \frac{\lambda e^2}{r^2} + \omega_L m - E \right) R(r) = 0$$

对比碱金属原子方程，有 $E_0 = -\frac{\mu e^4}{2\hbar^2 n'^2}$。

**$B = 0$ 时**，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。

**$B \neq 0$ 时**，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，**不简并**。