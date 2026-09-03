# 氢原子与碱金属原子

## 概率密度与角度分布

概率密度角度分布在 $(\theta, \varphi)$ 方向的立体角 $d\Omega$ 中电子的概率为：

$$|Y_{lm}(\theta, \varphi)|^2 d\Omega = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$$

关于径向概率分布：

$$P(r) = r^2 |R_{nl}(r)|^2$$

关于概率密度角度分布：

$$P(\theta, \varphi) = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$$

## 电流分布与磁矩

电流密度 = 电荷 × 概率流密度：

$$\vec{j}_c = (-e) \cdot \frac{i\hbar}{2m}(\psi \nabla \psi^* - \psi^* \nabla \psi)$$

其中：

$$\psi_{nlm}(r, \theta, \varphi) = NR_{nl}(r) P_l^m(\cos\theta) e^{im\varphi}$$

$R_{nl}(r)$、$P_l^m(\cos\theta)$ 为实函数，则 $j_r = 0$。

$$J = \int [\psi^* \hat{L}_z \psi - \psi \hat{L}_z \psi^*] d\tau = \frac{m\hbar}{\mu} |\psi|^2$$

$\vec{j}$ 是围绕 $z$ 轴的许多环形电流（在 $x$-$y$ 平面），$d\vec{\mu} = dI \times \vec{S}$。

环形电流的截面积：$(r d\theta) \times dr$，电流 $= j_\varphi \times r d\theta \, dr$。

磁矩：

$$d\mu = (r\sin\theta)^2 \pi \cdot j_\varphi \, dr \, d\theta$$

# 碱金属原子

碱金属原子的势能：

$$V(r) = -\frac{e^2}{r} \quad (\text{氢原子})$$

$$V(r) = -\frac{e^2}{r} - \frac{\lambda e^2}{r^2} \quad (\text{碱金属原子})$$

其中 $a_0 = \frac{\hbar^2}{\mu e^2}$。

径向方程：

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right) + \frac{2\mu}{\hbar^2}\left[E + \frac{e^2}{r} + \frac{\lambda e^2}{r^2} - \frac{l(l+1)\hbar^2}{2\mu r^2}\right] R(r) = 0$$

令 $l'(l'+1) = l(l+1) - 2\lambda$，则类比氢原子：

$$E_n = -\frac{\mu e^4}{2\hbar^2 n'^2}, \quad n' = n_r + l' + 1$$

$$l' = -\frac{1}{2} + \sqrt{\left(l + \frac{1}{2}\right)^2 - 2\lambda} = -\frac{1}{2} + \left(l + \frac{1}{2}\right)\sqrt{1 - \frac{2\lambda}{\left(l + \frac{1}{2}\right)^2}}$$

$l'$ 与 $l$ 有关，能级简并度为 $2l+1$。

# 电磁场中电荷粒子的哈密顿量

在电磁场中，存在带电量为 $q$，质量为 $m$ 的粒子，粒子受力：

$$\vec{F} = q\vec{E} + q\vec{v} \times \vec{B}$$

由 $\nabla \cdot \vec{B} = 0$，则引入 $\vec{A}$ 为矢势：

$$\vec{B} = \nabla \times \vec{A}, \quad \vec{E} = -\nabla \varphi - \frac{\partial \vec{A}}{\partial t}$$

其中 $\varphi$ 为电势。

$$\vec{A} = (A_x, A_y, A_z)$$

$$\nabla \times \vec{B} = \nabla(\nabla \cdot \vec{A}) - \nabla^2 \vec{A}$$

考虑 $A_x(x, y, z, t)$，则：

$$\frac{dA_x}{dt} = \frac{\partial A_x}{\partial t} + \frac{\partial A_x}{\partial x}\dot{x} + \frac{\partial A_x}{\partial y}\dot{y} + \frac{\partial A_x}{\partial z}\dot{z}$$

故：

$$F_x = q\left[-\frac{\partial \varphi}{\partial x} - \frac{\partial A_x}{\partial t} + \dot{y}\left(\frac{\partial A_y}{\partial x} - \frac{\partial A_x}{\partial y}\right) - \dot{z}\left(\frac{\partial A_x}{\partial z} - \frac{\partial A_z}{\partial x}\right)\right]$$

由 $\frac{d}{dt}(m\dot{x}) = F_x$，则：

$$\frac{d}{dt}(m\dot{x} + qA_x) = q\left(-\frac{\partial \varphi}{\partial x}\right) + q\dot{x}\frac{\partial A_x}{\partial x}$$

令 $U = q(\varphi - \vec{A} \cdot \vec{v})$，则：

$$\frac{\partial U}{\partial x} = q\left(\frac{\partial \varphi}{\partial x} - \frac{\partial \vec{A}}{\partial x} \cdot \vec{v}\right) = -q\dot{A}_x$$

由拉格朗日方程：

$$\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{x}}\right) - \frac{\partial L}{\partial x} = F_x = -q\frac{\partial}{\partial x}(\varphi - \vec{A} \cdot \vec{v})$$

其中 $T = \frac{1}{2}m\vec{v}^2$。

$$\frac{d}{dt}\left(\frac{\partial}{\partial \dot{x}}(T - q\varphi + q\vec{A} \cdot \vec{v})\right) - \frac{\partial}{\partial x}(T - q\varphi + q\vec{A} \cdot \vec{v}) = 0$$

$y$、$z$ 方向同理。

哈密顿量：

$$H = \sum p_i \dot{q}_i - L = (m\vec{v} + q\vec{A}) \cdot \vec{v} - \frac{1}{2}mv^2 - (-q\varphi + q\vec{A} \cdot \vec{v}) = \frac{1}{2}mv^2 + q\varphi = \frac{1}{2m}(\vec{p} - q\vec{A})^2 + q\varphi$$

考虑系统中心力场：

$$H = \frac{1}{2m}\vec{p}^2 - \frac{e^2}{r} + \cdots$$

# 补充：坐标系变换

## 典型空间中的度规

二维空间，线元：

$$ds^2 = (dx)^2 + (dy)^2 = (dx, dy)\begin{pmatrix} dx \\ dy \end{pmatrix} = g_{ij} dx^i dx^j$$

若取极坐标系 $(r, \varphi)$，$x = r\cos\varphi$，$y = r\sin\varphi$，则：

$$ds^2 = (dr\cos\varphi - r\sin\varphi \, d\varphi)^2 + (dr\sin\varphi + r\cos\varphi \, d\varphi)^2 = dr^2 + r^2(d\varphi)^2$$

$$ds^2 = g_{ij} dx^i dx^j, \quad G = \begin{pmatrix} 1 & 0 \\ 0 & r^2 \end{pmatrix}$$

三维欧氏空间，线元：

$$ds^2 = (dx)^2 + (dy)^2 + (dz)^2 = \sum_{ij} g_{ij} dx^i dx^j, \quad g = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$$

若取球坐标，即 $\{x^1, x^2, x^3\} = \{r, \theta, \varphi\}$：

$$x = r\sin\theta\cos\varphi, \quad y = r\sin\theta\sin\varphi, \quad z = r\cos\theta$$

$$G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2\sin^2\theta \end{pmatrix}$$

## 梯度算子

$$(ds)^2 = h_1^2(dq_1)^2 + h_2^2(dq_2)^2 + h_3^2(dq_3)^2$$

在 $q_2, q_3$ 不变而 $q_1$ 相差微小变量时，线元 $(ds)^2 = h_1^2(dq_1)^2$（正交曲线坐标）。

对标量函数 $u(q_1, q_2, q_3)$，在 $u$ 增长方向的梯度：

$$\nabla u = \frac{1}{h_1}\frac{\partial u}{\partial q_1}\vec{e}_1 + \frac{1}{h_2}\frac{\partial u}{\partial q_2}\vec{e}_2 + \frac{1}{h_3}\frac{\partial u}{\partial q_3}\vec{e}_3$$

### 笛卡尔坐标系中的表示

事实上，考虑 $\nabla u = \frac{\partial u}{\partial x}\vec{e}_x + \frac{\partial u}{\partial y}\vec{e}_y + \frac{\partial u}{\partial z}\vec{e}_z$。

于是有：

$$\left(\frac{\partial u}{\partial q_1}, \frac{\partial u}{\partial q_2}, \frac{\partial u}{\partial q_3}\right) = \left(\frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z}\right) \frac{\partial(x, y, z)}{\partial(q_1, q_2, q_3)}$$

即：

$$\frac{\partial(u, v, w)}{\partial(x, y, z)} = \frac{\partial(u, v, w)}{\partial(q_1, q_2, q_3)} \cdot \frac{\partial(q_1, q_2, q_3)}{\partial(x, y, z)}$$

$$\frac{\partial(u, v, w)}{\partial(x, y, z)} = \frac{1}{H_u H_v H_w} \frac{\partial(u, v, w)}{\partial(q_1, q_2, q_3)}$$

## 散度

向量场在闭合曲面的通量等于向量场的散度在曲面包围区域的体积分。

$$\oint_S \vec{a} \cdot d\vec{S} = \int_V \nabla \cdot \vec{a} \, dV$$

考虑平行于 $d\vec{S}$ 的四个面，在剩下两面中一个面的通量为：

$$\vec{a}(u, v, w) \cdot H_v H_w \, dv \, dw$$

两个面的通量之差为：

$$\frac{\partial}{\partial u}(a_u H_v H_w) \, du \, dv \, dw$$

同理，另外两个通量差为 $\frac{\partial}{\partial v}(a_v H_u H_w) \, du \, dv \, dw$ 和 $\frac{\partial}{\partial w}(a_w H_u H_v) \, du \, dv \, dw$。

$$\therefore (\nabla \cdot \vec{a}) \, dV = (\nabla \cdot \vec{a}) J \, du \, dv \, dw = \left[\frac{\partial}{\partial u}(a_u H_v H_w) + \frac{\partial}{\partial v}(a_v H_u H_w) + \frac{\partial}{\partial w}(a_w H_u H_v)\right] du \, dv \, dw$$

$$\nabla \cdot \vec{a} = \frac{1}{H_u H_v H_w}\left[\frac{\partial}{\partial u}(a_u H_v H_w) + \frac{\partial}{\partial v}(a_v H_u H_w) + \frac{\partial}{\partial w}(a_w H_u H_v)\right]$$

如 $(u, v, w) = (r, \theta, \varphi)$，则：

$$\nabla \cdot \vec{F} = \frac{1}{r^2\sin\theta}\left[\frac{\partial}{\partial r}(r^2\sin\theta \, F_r) + \frac{\partial}{\partial \theta}(\sin\theta \, F_\theta) + \frac{\partial}{\partial \varphi}(r F_\varphi)\right] = \frac{1}{r^2}\frac{\partial}{\partial r}(r^2 F_r) + \frac{1}{r\sin\theta}\frac{\partial}{\partial \theta}(\sin\theta \, F_\theta) + \frac{1}{r\sin\theta}\frac{\partial F_\varphi}{\partial \varphi}$$

## 旋度

$$\text{rot} \, \vec{a} = \lim_{S \to 0} \frac{\oint \vec{a} \cdot d\vec{l}}{S}, \quad \vec{a} = a_u \vec{e}_u + a_v \vec{e}_v + a_w \vec{e}_w$$

考虑 $\text{rot} \, \vec{a}$ 在 $u$ 轴上的投影，取 $\vec{n}$ 为正方向，$S$ 面是 $u = \text{常数}$，曲面 $S$ 中的曲线 $L$ 设为 $M_1 M_2 N_2 N_1$。

$$\int_{M_1 M_2} \vec{a} \cdot d\vec{l} = a(u, v, w) \cdot H_v \, dv = a_v(u, v, w) H_v(u, v, w) \, dv$$

$$\int_{M_2 N_2} \vec{a} \cdot d\vec{l} = a(u, v + dv, w) \cdot H_w \, d\omega = a_w(u, v + dv, w) H_w(u, v + dv, w) \, dw$$

$$\int_{N_2 N_1} \vec{a} \cdot d\vec{l} = -a(u, v, w + dw) \cdot H_v \, dv = -a_v(u, v, w + dw) H_v(u, v, w + dw) \, dv$$

$$\int_{N_1 M_1} \vec{a} \cdot d\vec{l} = -a(u, v, w) H_w \, dw = -a_w(u, v, w) H_w(u, v, w) \, dw$$

则：

$$\oint \vec{a} \cdot d\vec{l} = \left[\frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v)\right] dv \, dw$$

$$(\text{rot} \, \vec{a})_u \, dv \, dw = \frac{1}{H_v H_w}\left[\frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v)\right] dv \, dw$$

$$\text{rot} \, \vec{a} = \frac{1}{H_u H_v H_w} \begin{vmatrix} H_u \vec{e}_u & H_v \vec{e}_v & H_w \vec{e}_w \\ \frac{\partial}{\partial u} & \frac{\partial}{\partial v} & \frac{\partial}{\partial w} \\ H_u a_u & H_v a_v & H_w a_w \end{vmatrix}$$

# 简单塞曼效应

无外加电磁场时：

$$\hat{H} = \frac{\hat{p}^2}{2\mu} + V(r), \quad V(r) = -\frac{ke^2}{r} - \frac{\lambda k e^2}{r^2}$$

加入磁场 $\vec{B} = B_0 \vec{e}_z$：

$$\hat{H}' = \hat{H} + \hat{H}^{(0)} + \hat{H}'$$

电荷为 $q$，质量为 $\mu$ 的粒子在矢势 $\vec{A}$ 和标势 $\varphi$ 中：

$$\hat{H} = \frac{(\hat{p} - q\vec{A})^2}{2\mu} + V + q\varphi$$

选 $\vec{A} = \left(-\frac{B_0}{2}y, \frac{B_0}{2}x, 0\right)$，则：

$$\hat{H} = \frac{1}{2\mu}\left[\left(\hat{p}_x + \frac{qB_0}{2\mu}y\right)^2 + \left(\hat{p}_y - \frac{qB_0}{2\mu}x\right)^2 + \hat{p}_z^2\right] + V(r)$$

$$= \frac{\hat{p}^2}{2\mu} + \frac{qB_0}{2\mu}(\hat{L}_z) + \frac{q^2 B_0^2}{8\mu}(x^2 + y^2) + V(r)$$

其中 $\hat{L}_z = x\hat{p}_y - y\hat{p}_x$，$\rho^2 = x^2 + y^2$。

$$\hat{H}\psi_{nlm} = E_{nlm}\psi_{nlm}, \quad \psi_{nlm}(r, \theta, \varphi) = R_{nl}(r) Y_{lm}(\theta, \varphi)$$

则：

$$\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{d}{dr}\right) + \frac{2\mu}{\hbar^2}\left(E - V(r) - \frac{l(l+1)\hbar^2}{2\mu r^2}\right)\right] R(r) Y_{lm}(\theta, \varphi) = 0$$

于是有：

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}(E - V(r)) - \frac{l(l+1)}{r^2}\right] R(r) = 0$$

**注意**：左式 $= \frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right) - \left[\frac{l(l+1)}{r^2}\right] R + \frac{2\mu}{\hbar^2}(E - V) R = 0$

令 $E = E_0 + \omega_L m\hbar$，$E = E_0 + \omega_L m\hbar$，代入 $V(r) = -\frac{ke^2}{r} - \frac{\lambda ke^2}{r^2}$：

则：

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right) - \left[\frac{l(l+1)}{r^2} - \frac{2\mu}{\hbar^2}\left(\frac{ke^2}{r} + \frac{\lambda ke^2}{r^2}\right) - \frac{2\mu}{\hbar^2}(\omega_L m - E_0)\right] R(r) = 0$$

$$\frac{d^2R}{dr^2} + \frac{2}{r}\frac{dR}{dr} + \left[E_0 + \frac{ke^2}{r} + \frac{\lambda ke^2}{r^2}\right] R(r) = 0$$

对比碱金属原子方程，有：

$$E_0 = -\frac{\mu k^2 e^4}{2\hbar^2 n'^2}, \quad E = E_0 + \omega_L m\hbar$$

**$B = 0$ 时**，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。

**$B \neq 0$ 时**，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，不简并。

根据断点后的原文行，缺失段是曲面坐标中向量场沿曲线积分的推导。结合稿尾内容，应续在碱金属能级分裂之后，补全曲面积分部分。整理如下：

---

**$B = 0$ 时**，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。

**$B \neq 0$ 时**，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，不简并。

---

考虑向量场 $\mathbf{a}$ 在 $u$ 轴上的投影，取 $n$ 为正方向，$S$ 面是 $u = \text{常数}$ 的曲面。曲面 $S$ 中的曲线 $L$ 设为 $MM_2$，则：

$$SMm_2 \mathbf{a} \cdot d\mathbf{s} = a(u, v, w) \cdot d\mathbf{s} = a(u, v, w) \cdot H_v \, dv = a(v, w) H_v (u, v, w) \, dv$$

对于 $N_1$ 到 $N_2$ 的路径，有：

$$N_1 N_2 (u, v + \Delta v, w + \Delta w)$$

后文继续：

$$(91, 82, 93) \quad (81, 2 + d_2 92) (u, v, w) M M_2 (u, v + dv, w)$$

…= a(u, v, w) \cdot d\mathbf{s} = a(u, v, w) \cdot H_v \, dv = a(v, w) H_v (u, v, w) \, dv$$

对于 $$N_1$ 到 $N_2\$ 的路径，有：

$$N_1 N_2 (u, v + \Delta v, w + \Delta w)$$

后文继续：

$$(91, 82, 93) \quad (81, 2 + d_2 92) (u, v, w) M M_2 (u, v + dv, w)$$

---

Huau $H_v}_v}$ Hwaw

单中科技

---

简单塞曼效应

无外加电磁场时，$A = \nabla^2 + V(r)$，$V(r) = -k^2 - \lambda k_1^2$