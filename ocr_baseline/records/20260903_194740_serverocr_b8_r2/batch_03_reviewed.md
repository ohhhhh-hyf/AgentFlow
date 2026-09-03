# 华中科技大学

## 概率密度角度分布

在 $(0,4)$ 方向的立体角 $d\Omega$ 中电子的概率为 $|Y_{lm}(0,4)|^2 d\Omega = |Y_{lm}(0,4)|^2 \sin\theta\, d\theta\, d\phi$

$$Y_{lm}(0,4) = \Theta_{lm}(\theta)\Phi_m(\phi) = P_l^m(\cos\theta) \cdot e^{im\phi},\quad |Y_{lm}(0,4)|^2 d\Omega \propto [P_l^m(\cos\theta)]^2 d\Omega$$

只与 $l,m$ 有关。

关于径向概率分布：

$$P(r_0, r_0+dr) = \int r^2 \sin\theta\, d\theta\, d\phi\, dr = r_0^2 dr \int [\Phi(\theta,\phi)]^2 \sin\theta\, d\theta\, d\phi$$

关于概率密度角度分布：

$$P(\theta + d\theta; \phi + d\phi) = \int r^2 \sin\theta\, d\theta\, d\phi\, dr = |Y_{lm}(\theta,\phi)|^2 \sin\theta\, d\theta\, d\phi$$

## 电流分布与磁矩

电流密度 = 电荷 × 概率流密度

$$j = (-e) \cdot \frac{i\hbar}{2m} (\psi^* \nabla \psi - \psi \nabla \psi^*)$$

$$\nabla = \frac{\partial}{\partial r} \hat{e}_r + \frac{1}{r}\frac{\partial}{\partial \theta} \hat{e}_\theta + \frac{1}{r\sin\theta}\frac{\partial}{\partial \phi} \hat{e}_\phi$$

$$\psi_{nlm}(r,\theta,\phi) = N_{nl} R_{nl}(r) P_l^m(\cos\theta) e^{im\phi},\quad R_{nl}(r)、P_l^m(\cos\theta) \text{为实函数，则} \frac{\partial \psi}{\partial r} = \frac{\partial \psi}{\partial \theta} = 0$$

$$j_\phi = \frac{i\hbar}{2m} [\psi^* \frac{1}{r\sin\theta}\frac{\partial \psi}{\partial \phi} - \psi \frac{1}{r\sin\theta}\frac{\partial \psi^*}{\partial \phi}] = \frac{\hbar m}{m r \sin\theta} |\psi|^2 = -\frac{e\hbar m}{m r \sin\theta} |\psi|^2$$

是围绕 Z 轴的许多环形电流（在 x-y 平面），$dM = dI \times S$。

$$M = \int [\pi (r\sin\theta)^2 j_\phi r d\theta dr] \cdot \hat{e}_z = -\frac{e\hbar m}{2m} \int r^2 \sin\theta\, d\theta\, dr = [-\frac{e\hbar m}{2m} r^2 \sin\theta\, d\theta\, dr] \hat{e}_z$$

截面面积：$(r d\theta) \times dr$，电流 = $j_\phi \times r d\theta dr$

$$M_z = -\frac{e\hbar m}{2m} = -\mu_B m,\quad M_z = -\frac{e\hbar}{2m} m \text{为常量，磁矩在 Z 方向的投影是量子化的}$$

## 碱金属原子

$$V(r) = -\frac{Ze^2}{r},\quad k = \frac{Ze^2}{4\pi\varepsilon_0} \text{（氢原子）}\quad V(r) = -\frac{Ze^2}{r} - \frac{\lambda \hbar^2}{2m r^2} \text{（碱金属原子）}$$

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right) + \left[\frac{2m}{\hbar^2}\left(E + \frac{Ze^2}{r}\right) - \frac{l(l+1)}{r^2}\right] R(r) = 0 \quad \text{（径向方程）}$$

令 $l(l+1) - 2\lambda = l'(l'+1)$，则类比氢原子，$E_{nl} = -\frac{k^2 m}{2\hbar^2 n^2}$，$n = n_r + l' + 1$

$$l' = -\frac{1}{2} + \sqrt{(l+\frac{1}{2})^2 - 2\lambda} > -\frac{1}{2} + (l+\frac{1}{2})$$

$l'$ 与 $l$ 有关，能级简并度为 $2l+1$。

## 电磁场中电荷粒子的哈密顿量

在电磁场中，存在带电量为 $q$，质量为 $M$ 的粒子，粒子受力 $\vec{F} = q\vec{E} + q\vec{v} \times \vec{B}$

由 $\nabla \cdot \vec{B} = 0$，则引入 $\vec{A}$ 为矢势，$\vec{B} = \nabla \times \vec{A}$，$\vec{E} = -\nabla \phi - \frac{\partial \vec{A}}{\partial t}$

$$\vec{B} = \nabla \times \vec{A} = \left(\frac{\partial A_z}{\partial y} - \frac{\partial A_y}{\partial z}\right)\hat{e}_x + \left(\frac{\partial A_x}{\partial z} - \frac{\partial A_z}{\partial x}\right)\hat{e}_y + \left(\frac{\partial A_y}{\partial x} - \frac{\partial A_x}{\partial y}\right)\hat{e}_z$$

$$F_x = q\left[-\frac{\partial \phi}{\partial x} - \frac{\partial A_x}{\partial t} + v_y\left(\frac{\partial A_y}{\partial x} - \frac{\partial A_x}{\partial y}\right) - v_z\left(\frac{\partial A_x}{\partial z} - \frac{\partial A_z}{\partial x}\right)\right]$$

考虑 $A_x(x,y,z,t)$，则 $\frac{dA_x}{dt} = \frac{\partial A_x}{\partial t} + \dot{x}\frac{\partial A_x}{\partial x} + \dot{y}\frac{\partial A_x}{\partial y} + \dot{z}\frac{\partial A_x}{\partial z}$

故 $F_x = q\left[-\frac{\partial \phi}{\partial x} - \frac{\partial A_x}{\partial t} + v_x\frac{\partial A_x}{\partial x} + v_y\frac{\partial A_y}{\partial x} + v_z\frac{\partial A_z}{\partial x}\right] = -\frac{\partial}{\partial x} q(\phi - \vec{v} \cdot \vec{A}) - q\frac{dA_x}{dt}$

由拉格朗日方程：$\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{x}}\right) - \frac{\partial L}{\partial x} = F_x = -\frac{\partial}{\partial x} q(\phi - \vec{A} \cdot \vec{v}) - q\frac{dA_x}{dt}$

$$T = \frac{1}{2}mv^2$$

$$\frac{d}{dt}\left(\frac{\partial T}{\partial \dot{x}} + qA_x\right) - \frac{\partial}{\partial x}(T - q\phi + q\vec{A} \cdot \vec{v}) = 0 \Rightarrow \frac{d}{dt}\left(\frac{\partial T}{\partial \dot{x}}\right) - \frac{\partial}{\partial x}(T - q\phi + q\vec{A} \cdot \vec{v}) = 0,\quad y, z \text{同理}$$

$$L = T - U = \frac{1}{2}mv^2 - q(\phi - \vec{v} \cdot \vec{A}) \text{为拉格朗日量}$$

正则动量 $\vec{P} = \frac{\partial L}{\partial \vec{v}} = m\vec{v} + q\vec{A}$

哈密顿量 $H = \vec{P} \cdot \vec{v} - L = (m\vec{v} + q\vec{A}) \cdot \vec{v} - \left[\frac{1}{2}mv^2 - q(\phi - \vec{v} \cdot \vec{A})\right] = \frac{1}{2}mv^2 + q\phi = \frac{1}{2M}(\vec{P} - q\vec{A})^2 + q\phi$

考虑系统中心力场，$\vec{A} = \frac{1}{2}\vec{B} \times \vec{r}$，$H = \frac{1}{2M}(\vec{P} - q\vec{A})^2 + V + q\phi$

## 补充：坐标系变换

### 典型空间中的度规

二维空间，线元 $ds^2 = (dx)^2 + (dy)^2 = (dx\ dy)\begin{pmatrix}1 & 0 \\ 0 & 1\end{pmatrix}\begin{pmatrix}dx \\ dy\end{pmatrix} = \sum_{ij} g_{ij} dx^i dx^j$

$g_{ij}$ 即 $\begin{pmatrix}g_{11} & g_{12} \\ g_{21} & g_{22}\end{pmatrix}$ 第 $i$ 行第 $j$ 列元素，是二维欧氏空间的度规在直角坐标 $\{x^1, x^2\} = \{x, y\}$ 下的形式。

若取极坐标系 $\{r, \phi\}$，$x = r\cos\phi$，$y = r\sin\phi$，则 $ds^2 = (dr\cos\phi - r\sin\phi\, d\phi)^2 + (dr\sin\phi + r\cos\phi\, d\phi)^2 = (dr)^2 + r^2(d\phi)^2$

$$ds^2 = \sum_{ij} g_{ij} dx^i dx^j,\quad G = \begin{pmatrix}1 & 0 \\ 0 & r^2\end{pmatrix}$$

三维欧氏空间，线元 $ds^2 = (dx)^2 + (dy)^2 + (dz)^2 = \sum_{ij} g_{ij} dx^i dx^j$，$G = \begin{pmatrix}1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1\end{pmatrix}$

若取球坐标，即 $\{x^1, x^2, x^3\} = \{r, \theta, \phi\}$，$x = r\sin\theta\cos\phi$，$y = r\sin\theta\sin\phi$，$z = r\cos\theta$

$$ds^2 = (dr\ d\theta\ d\phi)\begin{pmatrix}1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2\sin^2\theta\end{pmatrix}\begin{pmatrix}dr \\ d\theta \\ d\phi\end{pmatrix} = \sum_{ij} g_{ij} dx^i dx^j,\quad G = \begin{pmatrix}1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2\sin^2\theta\end{pmatrix}$$

### 梯度算子

对于正交曲线坐标系，度规矩阵 $G$ 一定为对角矩阵，记作 $\text{diag}(h_1^2, h_2^2, h_3^2)$

$$h_i = \sqrt{\left(\frac{\partial x}{\partial q_i}\right)^2 + \left(\frac{\partial y}{\partial q_i}\right)^2 + \left(\frac{\partial z}{\partial q_i}\right)^2}$$

在 $q_2, q_3$ 不变而 $q_1$ 相差微小变量时，线元 $(ds_1)^2 = h_1^2 (dq_1)^2$（正交系 $(q_1, q_2, q_3)$）。

对标量函数 $U(q_1, q_2, q_3)$，在 $q_1$ 增长方向的梯度 $(\nabla U)_{q_1} = \frac{\partial U}{\partial s_1} = \frac{1}{h_1}\frac{\partial U}{\partial q_1}$

事实上，考虑 $\nabla U = \vec{F}$，$\vec{F} = F_u \hat{e}_u + F_v \hat{e}_v + F_w \hat{e}_w$，$F_u = \frac{\partial U}{\partial s_u} = \frac{1}{h_u}\frac{\partial U}{\partial u}$

于是有 $\nabla U = \frac{1}{h_u}\frac{\partial U}{\partial u}\hat{e}_u + \frac{1}{h_v}\frac{\partial U}{\partial v}\hat{e}_v + \frac{1}{h_w}\frac{\partial U}{\partial w}\hat{e}_w$

对于正交曲线坐标系，$\hat{e}_u = \frac{\partial \vec{r}}{\partial s_u} = \frac{1}{h_u}\frac{\partial \vec{r}}{\partial u}$，即 $\frac{\partial (u,v,w)}{\partial (x,y,z)}$

于是 $\nabla U = \frac{1}{h_u}\frac{\partial U}{\partial u}\hat{e}_u + \frac{1}{h_v}\frac{\partial U}{\partial v}\hat{e}_v + \frac{1}{h_w}\frac{\partial U}{\partial w}\hat{e}_w$

### 散度

向量场在闭合曲面的通量等于向量场的散度在曲面包围区域的体积分。

考虑以 $du, dv, dw$ 为边的平行六面体 $dV$，$\vec{F} = F_u \hat{e}_u + F_v \hat{e}_v + F_w \hat{e}_w$

$dV$ 的体积为 $\left|\frac{\partial (x,y,z)}{\partial (u,v,w)}\right| du\, dv\, dw = |J| du\, dv\, dw$

$\frac{\partial \vec{r}}{\partial u} = h_u \hat{e}_u$ 平行于 $dv$ 的四个面，在剩下两面中一个面的通量为 $\vec{F} \cdot \hat{n} dS$

两个面的通量之差为 $\frac{\partial}{\partial u}(F_u h_v h_w J) du\, dv\, dw = \frac{\partial}{\partial u}(F_u h_v h_w) du\, dv\, dw$

同理，另外两个通量差为 $\frac{\partial}{\partial v}(F_v h_u h_w J) du\, dv\, dw$，$\frac{\partial}{\partial w}(F_w h_u h_v J) du\, dv\, dw$

$$\oint \vec{F} \cdot d\vec{S} = \int (\nabla \cdot \vec{F}) dV = \int (\nabla \cdot \vec{F}) |J| du\, dv\, dw = \int \left[\frac{\partial}{\partial u}(F_u h_v h_w) + \frac{\partial}{\partial v}(F_v h_u h_w) + \frac{\partial}{\partial w}(F_w h_u h_v)\right] du\, dv\, dw$$

$$\Rightarrow \nabla \cdot \vec{F} = \frac{1}{h_u h_v h_w}\left[\frac{\partial}{\partial u}(F_u h_v h_w) + \frac{\partial}{\partial v}(F_v h_u h_w) + \frac{\partial}{\partial w}(F_w h_u h_v)\right]$$

如 $(u,v,w) = (r,\theta,\phi)$，则 $\nabla \cdot \vec{F} = \frac{1}{r^2\sin\theta}\left[\frac{\partial}{\partial r}(r^2\sin\theta\, F_r) + \frac{\partial}{\partial \theta}(r^2\sin\theta\, F_\theta) + \frac{\partial}{\partial \phi}(r^2\sin\theta\, F_\phi)\right] = \frac{1}{r^2}\frac{\partial}{\partial r}(r^2 F_r) + \frac{1}{r\sin\theta}\frac{\partial}{\partial \theta}(\sin\theta\, F_\theta) + \frac{1}{r\sin\theta}\frac{\partial F_\phi}{\partial \phi}$

### 旋度

$$\text{rot}\, \vec{a} = \lim_{\Delta S \to 0} \frac{\oint \vec{a} \cdot d\vec{s}}{\Delta S}$$

$\vec{a} = a_u \hat{e}_u + a_v \hat{e}_v + a_w \hat{e}_w$

考虑 $\text{rot}\, \vec{a}$ 在 $u$ 轴上的投影，取 $\hat{n}$ 为正方向，$S$ 面是 $u$ = 常数。曲面 $S$ 中的曲线 $L$ 设为 $M_1 M_2 N_2 N_1$

$$\oint_{M_1 M_2} \vec{a} \cdot d\vec{s} = \vec{a}(u,v,w) \cdot d\vec{s} = \vec{a}(u,v,w) \cdot h_v \hat{e}_v dv = a_v(u,v,w) h_v(u,v,w) dv$$

$$\oint_{M_2 N_2} \vec{a} \cdot d\vec{s} = a_w(u,v+dv,w) h_w(u,v+dv,w) dw$$

$$\oint_{N_2 N_1} \vec{a} \cdot d\vec{s} = -\vec{a}(u,v,w+dw) \cdot h_v \hat{e}_v dv = -a_v(u,v,w+dw) h_v(u,v,w+dw) dv$$

$$\oint_{N_1 M_1} \vec{a} \cdot d\vec{s} = -a_w(u,v,w) h_w(u,v,w) dw$$

则 $\oint \vec{a} \cdot d\vec{s} = \frac{\partial (a_w h_w)}{\partial v} dv\, dw - \frac{\partial (a_v h_v)}{\partial w} dv\, dw = \left[\frac{\partial (a_w h_w)}{\partial v} - \frac{\partial (a_v h_v)}{\partial w}\right] dv\, dw$

$$(\text{rot}\, \vec{a})_u = \frac{1}{h_v h_w}\left[\frac{\partial (a_w h_w)}{\partial v} - \frac{\partial (a_v h_v)}{\partial w}\right]$$

同理，$(\text{rot}\, \vec{a})_v = \frac{1}{h_u h_w}\left[\frac{\partial (a_u h_u)}{\partial w} - \frac{\partial (a_w h_w)}{\partial u}\right]$，$(\text{rot}\, \vec{a})_w = \frac{1}{h_u h_v}\left[\frac{\partial (a_v h_v)}{\partial u} - \frac{\partial (a_u h_u)}{\partial v}\right]$

$$\text{rot}\, \vec{a} = \frac{1}{h_u h_v h_w}\begin{vmatrix} h_u \hat{e}_u & h_v \hat{e}_v & h_w \hat{e}_w \\ \frac{\partial}{\partial u} & \frac{\partial}{\partial v} & \frac{\partial}{\partial w} \\ h_u a_u & h_v a_v & h_w a_w \end{vmatrix}$$

---

# 华中科技大学

## 简单塞曼效应

无外加电磁场时，$H_0 = \frac{P^2}{2m} + V(r)$，$V(r) = -\frac{k}{r} - \frac{\lambda \hbar^2}{2m r^2}$

加入磁场 $\vec{B} = B\hat{e}_z$，$\vec{A}' = \frac{1}{2}\vec{B} \times \vec{r}$，$H = H_0 + H'$（后证）

电荷为 $q$，质量为 $m$ 的粒子在矢势 $\vec{A}$ 和标势 $\phi$ 中，有 $H = \frac{1}{2m}|\vec{P} - q\vec{A}|^2 + V + q\phi$

对塞曼效应，$\phi = 0$，$V(r) = -\frac{k}{r} - \frac{\lambda \hbar^2}{2m r^2}$，磁场 $\vec{B} = \nabla \times \vec{A} = B\hat{e}_z$，$q = -e$，$\nabla \cdot \vec{A} = 0$ 满足库仑规范

选 $\vec{A} = \left(-\frac{1}{2}By, \frac{1}{2}Bx, 0\right)$，则 $H = \frac{1}{2m}\left[\left(P_x + \frac{eB}{2}y\right)^2 + \left(P_y - \frac{eB}{2}x\right)^2 + P_z^2\right] + V(r)$

$$H = \frac{P^2}{2m} + \frac{eB}{2m}(xP_y - yP_x) + \frac{e^2 B^2}{8m}(x^2 + y^2) + V(r)$$

令 $\omega_L = \frac{eB}{2m}$，$\rho^2 = x^2 + y^2$，又 $L_z = xP_y - yP_x$

则 $H = \frac{P^2}{2m} + \omega_L L_z + \frac{1}{2}m\omega_L^2 \rho^2 + V(r)$。$\omega_L \rho^2 \ll \omega_L$，可忽略 $\Rightarrow H = \frac{P^2}{2m} + \omega_L L_z + V(r) = H_0 + H'$

$$H\psi_{nlm} = E_{nlm} \psi_{nlm}(r,\theta,\phi) = R_{nl}(r) Y_{lm}(\theta,\phi)$$

则 $\left[-\frac{\hbar^2}{2m}\nabla^2 + V(r) + \omega_L L_z\right] R_{nl}(r) Y_{lm}(\theta,\phi) = \left[-\frac{\hbar^2}{2m}\nabla^2 + V(r) + \omega_L m\hbar\right] R_{nl}(r) Y_{lm}(\theta,\phi) = E R_{nl}(r) Y_{lm}(\theta,\phi)$

于是有 \$\left[-\frac{\hbar^2}{2m}\frac{