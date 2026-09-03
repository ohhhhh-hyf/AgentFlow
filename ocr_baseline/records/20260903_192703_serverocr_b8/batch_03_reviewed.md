# 华中科技大学 量子力学笔记

## 概率密度角度分布

在 $(0, \phi)$ 方向的立体角 $d\Omega$ 中电子的概率为 $|Y_{lm}(\theta, \phi)|^2 d\Omega = |Y_{lm}(\theta, \phi)|^2 \sin\theta \, d\theta \, d\phi$

$$Y_{lm}(\theta, \phi) = \Theta_{lm}(\theta) \Phi_m(\phi) = P_l^m(\cos\theta) \cdot e^{im\phi}, \quad |Y_{lm}(\theta, \phi)|^2 d\Omega \propto [P_l^m(\cos\theta)]^2 d\Omega$$

只与 $l, m$ 有关。

关于径向概率分布：

$$P(r_0, r_0 + dr) = \int r^2 \sin\theta \, d\theta \, d\phi \, dr \cdot |R_{nl}(r)|^2 = r_0^2 dr \int [|R_{nl}(r)|^2 \sin\theta \, d\theta \, d\phi]$$

关于概率密度角度分布：

$$P(\theta + d\theta; \phi + d\phi) = \int r^2 \sin\theta \, d\theta \, d\phi \, dr \cdot |Y_{lm}(\theta, \phi)|^2 \sin\theta \, d\theta \, d\phi$$

## 电流分布与磁矩

电流密度 = 电荷 × 概率流密度

$$\mathbf{j} = (-e) \cdot \frac{i\hbar}{2m} (\psi^* \nabla \psi - \psi \nabla \psi^*)$$

$$\nabla = \mathbf{e}_r \frac{\partial}{\partial r} + \mathbf{e}_\theta \frac{1}{r} \frac{\partial}{\partial \theta} + \mathbf{e}_\phi \frac{1}{r \sin\theta} \frac{\partial}{\partial \phi}$$

$$\psi_{nlm}(r, \theta, \phi) = N_{nl} R_{nl}(r) P_l^m(\cos\theta) e^{im\phi}, \quad R_{nl}(r)、P_l^m(\cos\theta) \text{为实函数，则} \frac{\partial \psi}{\partial r} = \frac{\partial \psi}{\partial \theta} = 0$$

$$j_\phi = \frac{i\hbar}{2m} [\psi^* \frac{1}{r \sin\theta} \frac{\partial \psi}{\partial \phi} - \psi \frac{1}{r \sin\theta} \frac{\partial \psi^*}{\partial \phi}] = \frac{\hbar m}{m r \sin\theta} |\psi|^2 = -\frac{e\hbar m}{m r \sin\theta} |\psi|^2$$

是围绕 Z 轴的许多环形电流（在 x-y 平面），$dM = dI \times S$。

$$M = \int [\pi (r \sin\theta)^2 j_\phi r \, d\theta \, dr] \cdot \mathbf{e}_z = -\frac{e\hbar m}{2m} \int r^2 \sin\theta \, dr \, d\theta \cdot \mathbf{e}_z = [-\frac{e\hbar m}{2m} \int r^2 \sin\theta \, dr \, d\theta] \mathbf{e}_z$$

截面面积：$(r d\theta) \times dr$，电流 = $j_\phi \times r d\theta \, dr$

$$M_z = -\frac{e\hbar m}{2m} = -\mu_B m, \quad M_z = -\frac{e\hbar}{2m} m \text{为常量，磁矩在 Z 方向的投影是量子化的}$$

## 碱金属原子

$$V(r) = -\frac{Z e^2}{r}, \quad k = \frac{Z e^2}{4\pi\varepsilon_0} \text{（氢原子）} \quad V(r) = -\frac{Z e^2}{r} - \frac{\lambda \hbar^2}{2m r^2} \text{（碱金属原子）} \quad a_0 = \frac{\hbar^2}{m e^2}$$

$$\frac{1}{r^2} \frac{d}{dr} \left( r^2 \frac{dR}{dr} \right) + \left[ \frac{2m}{\hbar^2} \left( E + \frac{Z e^2}{r} + \frac{\lambda \hbar^2}{2m r^2} \right) - \frac{l(l+1)}{r^2} \right] R(r) = 0 \quad \text{（径向方程）}$$

$$\frac{1}{r^2} \frac{d}{dr} \left( r^2 \frac{dR}{dr} \right) + \left[ \frac{2m}{\hbar^2} \left( E + \frac{Z e^2}{r} \right) - \frac{l(l+1) - 2\lambda}{r^2} \right] R(r) = 0$$

令 $l(l+1) - 2\lambda = l'(l'+1)$，则类比氢原子，$E_{nl} = -\frac{Z^2 e^4 m}{2\hbar^2 n^2}$，$n = n_r + l' + 1$

$$l' = -\frac{1}{2} + \sqrt{(l + \frac{1}{2})^2 - 2\lambda} > -1/2 + (l+1)$$

$l'$ 与 $l$ 有关，能级简并度为 $2l+1$。

## 电磁场中电荷粒子的哈密顿量

在电磁场中，存在带电量为 $q$，质量为 $M$ 的粒子，粒子受力 $\mathbf{F} = q\mathbf{E} + q\mathbf{v} \times \mathbf{B}$

### 电势

由 $\nabla \cdot \mathbf{B} = 0$，则引入 $\mathbf{A}$ 为矢势，$\mathbf{B} = \nabla \times \mathbf{A}$，$\mathbf{E} = -\nabla \phi - \frac{\partial \mathbf{A}}{\partial t}$（$\nabla \cdot \mathbf{B} = 0$，$\nabla \times \mathbf{E} = -\frac{\partial \mathbf{B}}{\partial t}$）

$$\mathbf{B} = \nabla \times \mathbf{A} = \begin{vmatrix} \mathbf{i} & \mathbf{j} & \mathbf{k} \\ \frac{\partial}{\partial x} & \frac{\partial}{\partial y} & \frac{\partial}{\partial z} \\ A_x & A_y & A_z \end{vmatrix} = \left( \frac{\partial A_z}{\partial y} - \frac{\partial A_y}{\partial z} \right) \mathbf{i} + \left( \frac{\partial A_x}{\partial z} - \frac{\partial A_z}{\partial x} \right) \mathbf{j} + \left( \frac{\partial A_y}{\partial x} - \frac{\partial A_x}{\partial y} \right) \mathbf{k}$$

$$F_x = q \left[ -\frac{\partial \phi}{\partial x} - \frac{\partial A_x}{\partial t} + v_y \left( \frac{\partial A_y}{\partial x} - \frac{\partial A_x}{\partial y} \right) - v_z \left( \frac{\partial A_x}{\partial z} - \frac{\partial A_z}{\partial x} \right) \right]$$

考虑 $A_x(x, y, z, t)$，则 $\frac{dA_x}{dt} = \frac{\partial A_x}{\partial t} + \frac{\partial A_x}{\partial x} \dot{x} + \frac{\partial A_x}{\partial y} \dot{y} + \frac{\partial A_x}{\partial z} \dot{z}$

故 $F_x = q \left[ -\frac{\partial \phi}{\partial x} - \frac{\partial A_x}{\partial t} + v_x \frac{\partial A_x}{\partial x} + v_y \frac{\partial A_y}{\partial x} + v_z \frac{\partial A_z}{\partial x} \right] = -\frac{\partial}{\partial x} q(\phi - \mathbf{v} \cdot \mathbf{A}) - q \frac{dA_x}{dt}$

由 $\frac{d}{dt} \left( \frac{\partial T}{\partial \dot{x}} \right) = \frac{d}{dt} (m\dot{x} + qA_x) = -\frac{\partial}{\partial x} q(\phi - \mathbf{A} \cdot \mathbf{v}) + q \frac{\partial}{\partial x} (\mathbf{v} \cdot \mathbf{A})$

令 $U = q(\phi - \mathbf{A} \cdot \mathbf{v})$，则 $\frac{\partial U}{\partial \dot{x}} = -qA_x$，$\frac{\partial U}{\partial \dot{y}} = -qA_y$，$\frac{\partial U}{\partial \dot{z}} = -qA_z$

由拉格朗日方程：$\frac{d}{dt} \left( \frac{\partial L}{\partial \dot{x}} \right) - \frac{\partial L}{\partial x} = F_x = -\frac{\partial}{\partial x} q(\phi - \mathbf{A} \cdot \mathbf{v}) - q \frac{dA_x}{dt}$

$$T = \frac{1}{2} mv^2$$

$$\frac{d}{dt} \left( \frac{\partial T}{\partial \dot{x}} + qA_x \right) - \frac{\partial}{\partial x} (T - q\phi + q\mathbf{A} \cdot \mathbf{v}) = 0 \Rightarrow \frac{d}{dt} \left( \frac{\partial T}{\partial \dot{x}} \right) - \frac{\partial}{\partial x} (T - q\phi + q\mathbf{A} \cdot \mathbf{v}) = 0, \quad y, z \text{同理}$$

$$L = T - U = \frac{1}{2} mv^2 - q(\phi - \mathbf{v} \cdot \mathbf{A}) \text{为拉格朗日量}$$

正则动量 $\mathbf{P} = \frac{\partial L}{\partial \mathbf{v}} = m\mathbf{v} + q\mathbf{A}$

哈密顿量 $H = \mathbf{P} \cdot \mathbf{v} - L = (m\mathbf{v} + q\mathbf{A}) \cdot \mathbf{v} - \left[ \frac{1}{2} mv^2 - q(\phi - \mathbf{v} \cdot \mathbf{A}) \right] = \frac{1}{2} mv^2 + q\phi = \frac{1}{2M} (\mathbf{P} - q\mathbf{A})^2 + q\phi$

考虑系统中心力场，$\mathbf{A} = \frac{1}{2} \mathbf{B} \times \mathbf{r}$，$H = \frac{1}{2M} (\mathbf{P} - q\mathbf{A})^2 + V + q\phi$

## 补充：坐标系变换

### 典型空间中的度规

二维空间，线元 $ds^2 = (dx)^2 + (dy)^2 = (dx \ dy) \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix} \begin{pmatrix} dx \\ dy \end{pmatrix} = \sum_{ij} g_{ij} dx^i dx^j$

$g_{ij}$ 即 $\begin{pmatrix} g_{11} & g_{12} \\ g_{21} & g_{22} \end{pmatrix}$ 第 $i$ 行第 $j$ 列元素，是二维欧氏空间的度规在直角坐标 $\{x^1, x^2\} = \{x, y\}$ 下的形式。

若取极坐标系 $\{r, \phi\}$，$x = r\cos\phi$，$y = r\sin\phi$，则 $ds^2 = (dr\cos\phi - r\sin\phi \, d\phi)^2 + (dr\sin\phi + r\cos\phi \, d\phi)^2 = (dr)^2 + r^2 (d\phi)^2$

$$ds^2 = \sum_{ij} g_{ij} dx^i dx^j, \quad G = \begin{pmatrix} 1 & 0 \\ 0 & r^2 \end{pmatrix}$$

三维欧氏空间，线元 $ds^2 = (dx)^2 + (dy)^2 + (dz)^2 = \sum_{ij} g_{ij} dx^i dx^j$，$G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$

若取球坐标，即 $\{x^1, x^2, x^3\} = \{r, \theta, \phi\}$，$x = r\sin\theta\cos\phi$，$y = r\sin\theta\sin\phi$，$z = r\cos\theta$

$$ds^2 = (dr \ d\theta \ d\phi) \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2 \sin^2\theta \end{pmatrix} \begin{pmatrix} dr \\ d\theta \\ d\phi \end{pmatrix} = \sum_{ij} g_{ij} dx^i dx^j, \quad G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2 \sin^2\theta \end{pmatrix}$$

### 梯度算子

对于正交曲线坐标系，度规矩阵 $G$ 一定为对角矩阵，记作 $\text{diag}(h_1^2, h_2^2, h_3^2)$

$$h_i = \sqrt{\left( \frac{\partial x}{\partial q_i} \right)^2 + \left( \frac{\partial y}{\partial q_i} \right)^2 + \left( \frac{\partial z}{\partial q_i} \right)^2}$$

在 $q_2, q_3$ 不变而 $q_1$ 相差微小变量时，线元 $(ds_1)^2 = h_1^2 (dq_1)^2$（正交系 $(q_1, q_2, q_3)$）。

对标量函数 $U(q_1, q_2, q_3)$，在 $q_1$ 增长方向的梯度 $(\nabla U)_{q_1} = \frac{\partial U}{\partial s_1} = \frac{1}{h_1} \frac{\partial U}{\partial q_1}$

#### 梯度在笛卡尔坐标系中的表示

事实上，考虑 $\nabla U = \mathbf{F}$，$\mathbf{F} = F_u \mathbf{e}_u + F_v \mathbf{e}_v + F_w \mathbf{e}_w$，$F_u = \frac{1}{h_u} \frac{\partial U}{\partial u} = \left( \frac{\partial U}{\partial x} \right) \frac{\partial x}{\partial s_u} + \left( \frac{\partial U}{\partial y} \right) \frac{\partial y}{\partial s_u} + \left( \frac{\partial U}{\partial z} \right) \frac{\partial z}{\partial s_u}$

于是有 $\left( \frac{\partial U}{\partial x}, \frac{\partial U}{\partial y}, \frac{\partial U}{\partial z} \right)$

$$\left( \frac{\partial U}{\partial u}, \frac{\partial U}{\partial v}, \frac{\partial U}{\partial w} \right) = \left( \frac{\partial U}{\partial x}, \frac{\partial U}{\partial y}, \frac{\partial U}{\partial z} \right) \begin{pmatrix} \frac{\partial x}{\partial u} & \frac{\partial y}{\partial u} & \frac{\partial z}{\partial u} \\ \frac{\partial x}{\partial v} & \frac{\partial y}{\partial v} & \frac{\partial z}{\partial v} \\ \frac{\partial x}{\partial w} & \frac{\partial y}{\partial w} & \frac{\partial z}{\partial w} \end{pmatrix}$$

对于正交曲线坐标系，$\mathbf{e}_u = \frac{1}{h_u} \frac{\partial \mathbf{r}}{\partial u}$，即 $\frac{\partial (u, v, w)}{\partial (x, y, z)}$

$$\left( \frac{\partial U}{\partial u}, \frac{\partial U}{\partial v}, \frac{\partial U}{\partial w} \right) = \left( \frac{\partial U}{\partial x}, \frac{\partial U}{\partial y}, \frac{\partial U}{\partial z} \right) \begin{pmatrix} h_u \mathbf{e}_u \\ h_v \mathbf{e}_v \\ h_w \mathbf{e}_w \end{pmatrix}$$

于是 $\nabla U = \frac{1}{h_u} \frac{\partial U}{\partial u} \mathbf{e}_u + \frac{1}{h_v} \frac{\partial U}{\partial v} \mathbf{e}_v + \frac{1}{h_w} \frac{\partial U}{\partial w} \mathbf{e}_w$

### 散度

向量场在闭合曲面的通量等于向量场的散度在曲面包围区域的体积分。

考虑以 $du, dv, dw$ 为边的平行六面体 $dV$，$\mathbf{F} = F_u \mathbf{e}_u + F_v \mathbf{e}_v + F_w \mathbf{e}_w$

$dV$ 的体积为 $\left\| \frac{\partial (x, y, z)}{\partial (u, v, w)} \right\| du \, dv \, dw = |J| du \, dv \, dw$

$\mathbf{e}_u = \frac{1}{h_u} \frac{\partial \mathbf{r}}{\partial u}$ 平行于 $dv$ 的四个面，在剩下两面中一个面的通量为 $\mathbf{F} \cdot \mathbf{n} \, dS$

两个面的通量之差为 $\frac{\partial}{\partial u} (F_u |J| \, dv \, dw) \cdot du = \frac{\partial}{\partial u} (F_u |J|) du \, dv \, dw$

同理，另外两个通量差为 $\frac{\partial}{\partial v} (F_v |J|) du \, dv \, dw$，$\frac{\partial}{\partial w} (F_w |J|) du \, dv \, dw$

$$\oint \mathbf{F} \cdot d\mathbf{S} = \int (\nabla \cdot \mathbf{F}) dV = \int (\nabla \cdot \mathbf{F}) |J| du \, dv \, dw = \int \left[ \frac{\partial}{\partial u} (F_u |J|) + \frac{\partial}{\partial v} (F_v |J|) + \frac{\partial}{\partial w} (F_w |J|) \right] du \, dv \, dw$$

$$\Rightarrow \nabla \cdot \mathbf{F} = \frac{1}{|J|} \left[ \frac{\partial}{\partial u} (F_u |J|) + \frac{\partial}{\partial v} (F_v |J|) + \frac{\partial}{\partial w} (F_w |J|) \right] = \frac{1}{h_u h_v h_w} \left[ \frac{\partial}{\partial u} (F_u h_v h_w) + \frac{\partial}{\partial v} (F_v h_u h_w) + \frac{\partial}{\partial w} (F_w h_u h_v) \right]$$

如 $(u, v, w) = (r, \theta, \phi)$，则 $\nabla \cdot \mathbf{F} = \frac{1}{r^2 \sin\theta} \left[ \frac{\partial}{\partial r} (r^2 \sin\theta \, F_r) + \frac{\partial}{\partial \theta} (r^2 \sin\theta \, F_\theta) + \frac{\partial}{\partial \phi} (r^2 \sin\theta \, F_\phi) \right] = \frac{1}{r^2} \frac{\partial}{\partial r} (r^2 F_r) + \frac{1}{r \sin\theta} \frac{\partial}{\partial \theta} (\sin\theta \, F_\theta) + \frac{1}{r \sin\theta} \frac{\partial F_\phi}{\partial \phi}$

### 旋度

$$\text{rot} \, \mathbf{a} = \lim_{\Delta S \to 0} \frac{\oint \mathbf{a} \cdot d\mathbf{s}}{\Delta S}$$

$$\mathbf{a} = a_u \mathbf{e}_u + a_v \mathbf{e}_v + a_w \mathbf{e}_w$$

考虑 $\text{rot} \, \mathbf{a}$ 在 $u$ 轴上的投影，取 $\mathbf{n}$ 为正方向，$S$ 面是 $u$ = 常数。曲面 $S$ 中的曲线 $L$ 设为 $M_1 M_2 N_2 N_1$

$$\oint_{M_1 N_1} \mathbf{a} \cdot d\mathbf{s} = \mathbf{a}(u, v, w) \cdot d\mathbf{s} = \mathbf{a}(u, v, w) \cdot H_v \mathbf{e}_v \cdot dv = a_v(u, v, w) H_v(u, v, w) dv$$

$$\oint_{M_2 N_2} \mathbf{a} \cdot d\mathbf{s} = a_2(u, v + dv, w) \cdot d\mathbf{s} = a_w(u, v + dv, w) H_w dw \mathbf{e}_w = a_w(u, v + dv, w) H_w(u, v + dv, w) dw$$

$$\oint_{N_2 N_1} \mathbf{a} \cdot d\mathbf{s} = a(u, v, w + dw) d\mathbf{s} = -a_v(u, v, w + dw) H_v dv \mathbf{e}_v = -a_v(u, v, w + dw) H_v(u, v, w + dw) dv$$

$$\oint_{M_1 M_2} \mathbf{a} \cdot d\mathbf{s} = -a(u, v, w) H_w dw \mathbf{e}_w = -a_w(u, v, w) H_w(u, v, w) dw$$

则 \$\oint \mathbf{a} \cdot d\mathbf{s} = \frac{\partial (a_w H_w)}{\partial v} dv \, dw - \frac{\partial (a_v H_v)}{\partial w