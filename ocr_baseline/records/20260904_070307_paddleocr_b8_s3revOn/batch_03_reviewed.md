## 概率密度与角度分布

概率密度角度分布在 $(\theta, \varphi)$ 方向的立体角 $d\Omega$ 中电子的概率为：

$$|Y_{lm}(\theta, \varphi)|^2 d\Omega = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$$

关于径向概率分布：

$$P(r) = r^2 |R_{nl}(r)|^2 \, dr$$

关于概率密度角度分布：

$$P(\theta, \varphi) \, d\theta \, d\varphi = \int |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$$

## 电流分布与磁矩

电流密度 = 电荷 × 概率流密度：

$$\vec{j}_c = (-e) \cdot \frac{i\hbar}{2m} (\psi^* \nabla \psi - \psi \nabla \psi^*)$$

其中：

$$\psi_{nlm}(r, \theta, \varphi) = N R_{nl}(r) P_l^m(\cos\theta) e^{im\varphi}$$

若 $R_{nl}(r) P_l^m(\cos\theta)$ 为实函数，则：

$$\vec{j} = \frac{e\hbar m}{m_e r \sin\theta} |\psi_{nlm}|^2 \hat{e}_\varphi$$

即围绕 $z$ 轴的许多环形电流（在 $x$-$y$ 平面内），$d\vec{\mu} = dI \times \vec{S}$。

其中：

$$d(r\sin\theta) \times d(r\cos\theta)$$

截面面积：$(r\, d\theta) \times dr$，电流 $= j_\varphi \times r\, d\theta \, dr$。

## 碱金属原子

碱金属原子的势场与氢原子不同，其径向方程为：

$$V(r)=-\frac{e^2}{r} \quad (\text{碱金属原子}) \quad a_0=\frac{\hbar^2}{me^2}$$

$$\left[\frac{d^2}{dr^2}+\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{r}\right)-\frac{l(l+1)}{r^2}\right]R_l(r)=0 \quad (\text{径向方程})$$

$$\left[\frac{d^2}{dr^2}+\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{r}\right)-\frac{l'(l'+1)}{r^2}\right]R(r)=0$$

令 $l'(l'+1)-2\lambda=l(l+1)$，则类比氢原子：

$$E_n=-\frac{me^4}{2\hbar^2 n^2}, \quad n=n_r+l+1$$

$$l'=-\frac{1}{2}+\sqrt{\left(l+\frac{1}{2}\right)^2-2\lambda}=-\frac{1}{2}+\left(l+\frac{1}{2}\right)\sqrt{1-\frac{2\lambda}{\left(l+\frac{1}{2}\right)^2}}$$

$l'$ 与 $l$ 有关，能级简并度为 $2l+1$。

---

## 电磁场中电荷粒子的哈密顿量

在电磁场中，存在带电量为 $q$，质量为 $m$ 的粒子，粒子受力：

$$\mathbf{F}=q\mathbf{E}+q\mathbf{v}\times\mathbf{B}$$

由 $\nabla\cdot\mathbf{B}=0$，则引入 $\mathbf{A}$ 为矢势：

$$\mathbf{B}=\nabla\times\mathbf{A}, \quad \mathbf{E}=-\nabla\phi-\frac{\partial\mathbf{A}}{\partial t} \quad (\nabla\times\mathbf{E}=-\frac{\partial\mathbf{B}}{\partial t}) \quad \phi \text{ 为电势}$$

$$\mathbf{A}=(A_x, A_y, A_z)$$

$$\nabla\times\mathbf{B}=\nabla(\nabla\cdot\mathbf{A})-\nabla^2\mathbf{A}$$

$$B_x=\frac{\partial A_z}{\partial y}-\frac{\partial A_y}{\partial z}, \quad B_y=\frac{\partial A_x}{\partial z}-\frac{\partial A_z}{\partial x}, \quad B_z=\frac{\partial A_y}{\partial x}-\frac{\partial A_x}{\partial y}$$

$$F_x=q\left[-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+v_y\left(\frac{\partial A_y}{\partial x}-\frac{\partial A_x}{\partial y}\right)-v_z\left(\frac{\partial A_x}{\partial z}-\frac{\partial A_z}{\partial x}\right)\right]$$

考虑 $A_x(x,y,z,t)$，则：

$$\frac{dA_x}{dt}=\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}$$

故：

$$F_x=q\left[-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}\right]=q\left(-\frac{\partial\phi}{\partial x}-\frac{dA_x}{dt}+\frac{\partial A_x}{\partial x}\dot{x}\right)$$

由 $\frac{d}{dt}(m\dot{x})=F_x$，则：

$$\frac{d}{dt}(m\dot{x}+qA_x)=q\left(-\frac{\partial\phi}{\partial x}\right)+q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})$$

令 $U=q(\phi-\mathbf{A}\cdot\mathbf{v})$，则：

$$\frac{\partial U}{\partial x}=q\frac{\partial\phi}{\partial x}-q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})=-q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})+q\frac{\partial\phi}{\partial x}$$

$$\frac{\partial U}{\partial \dot{x}}=-qA_x, \quad \frac{\partial U}{\partial \dot{y}}=-qA_y, \quad \frac{\partial U}{\partial \dot{z}}=-qA_z$$

由拉格朗日方程：

$$\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{x}}\right)-\frac{\partial L}{\partial x}=F_x=-q\frac{\partial}{\partial x}(\phi-\mathbf{A}\cdot\mathbf{v})$$

$$T=\frac{1}{2}m\dot{x}^2$$

$$\frac{d}{dt}\left(\frac{\partial}{\partial \dot{x}}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})\right)-\frac{\partial}{\partial x}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})=0$$

对 $y$、$z$ 同理。

$$\frac{d}{dt}(m\dot{x}+qA_x)$$

## 哈密顿量

哈密顿量 $H = -L = (m\mathbf{v} + q\mathbf{A}) \cdot \mathbf{v} - \frac{1}{2}mv^2 - (-V + \mathbf{A} \cdot \mathbf{v}) = \frac{1}{2}mv^2 + q\varphi = \frac{1}{2m}(\mathbf{P} - q\mathbf{A})^2 + q\varphi$

考虑系统中心力场，$H = \frac{1}{2}m\dot{r}^2 - \frac{A^2}{r} + V(r)$

## 补充：坐标系变换

### 典型空间中的度规

二维空间，线元 $ds^2 = (dx)^2 + (dy)^2 = (dx\ dy) \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix} \begin{pmatrix} dx \\ dy \end{pmatrix} = g_{ij} dx^i dx^j$

若取极坐标系 $r, \varphi$，$x = r\cos\varphi$，$y = r\sin\varphi$，则

$$ds^2 = (dr\cos\varphi - r\sin\varphi\, d\varphi)^2 + (dr\sin\varphi + r\cos\varphi\, d\varphi)^2 = dr^2 + r^2 d\varphi^2$$

$$ds^2 = g_{ij} dx^i dx^j, \quad G = \begin{pmatrix} 1 & 0 \\ 0 & r^2 \end{pmatrix}$$

三维欧氏空间，线元 $ds^2 = (dx)^2 + (dy)^2 + (dz)^2 = \sum_{ij} \delta_{ij} dx^i dx^j$，$\delta = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$

若取球坐标，即 $\{x^1, x^2, x^3\} = \{r, \theta, \varphi\}$，$x = r\sin\theta\cos\varphi$，$y = r\sin\theta\sin\varphi$，$z = r\cos\theta$，则

$$G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2\sin^2\theta \end{pmatrix}$$

### 梯度算子

$h_i = \sqrt{g_{ii}}$，在 $x^2, x^3$ 不变而 $x^1$ 相差微小变量时，线元 $(ds)^2 = h_1^2 (dq^1)^2$（正交坐标系）。

对标量函数 $u(x^1, x^2, x^3)$，在增长方向的梯度 $(\nabla u)_i = \frac{1}{h_i} \frac{\partial u}{\partial x^i} \mathbf{e}_i$

#### 笛卡尔坐标系中的表示

事实上，考虑 $\nabla u = \frac{\partial u}{\partial x} \mathbf{e}_x + \frac{\partial u}{\partial y} \mathbf{e}_y + \frac{\partial u}{\partial z} \mathbf{e}_z$

于是有 $\left( \frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z} \right) = \left( \frac{\partial u}{\partial r}, \frac{\partial u}{\partial \theta}, \frac{\partial u}{\partial \varphi} \right) \frac{\partial (x, y, z)}{\partial (r, \theta, \varphi)}$

即

$$\frac{\partial (u, v, w)}{\partial (x, y, z)} = \frac{\partial (u, v, w)}{\partial (r, \theta, \varphi)} \cdot \frac{\partial (r, \theta, \varphi)}{\partial (x, y, z)}$$

$$\frac{\partial (u, v, w)}{\partial (x, y, z)} = \frac{\partial (u, v, w)}{\partial (r, \theta, \varphi)} \cdot \frac{\partial (r, \theta, \varphi)}{\partial (x, y, z)}$$

## 散度

向量场在闭合曲面的通量等于向量场的散度在曲面包围区域的体积分。

设 $F = P\mathbf{e}_u + Q\mathbf{e}_v + R\mathbf{e}_w$，考虑平行于 $d$ 的四个面，在剩下两面中一个面的通量为：

$$(x, y, z)(x, y, w) \quad K = \frac{\partial}{\partial u}(\cdot)$$

两个面的通量之差为 $(J_b \, dv \, dw) \cdot du = \frac{\partial}{\partial u}(J) \, du \, dv \, dw$。

同理，另外两个通量差为 $\frac{\partial}{\partial v}(\cdot) \, du \, dv \, dw$，$\frac{\partial}{\partial w}(\cdot) \, du \, dv \, dw$。

$$\therefore (\nabla \cdot F) \, dV = (\nabla \cdot F) J \, du \, dv \, dw = \left[ \frac{\partial}{\partial u}(\cdot) + \frac{\partial}{\partial v}(\cdot) + \frac{\partial}{\partial w}(\cdot) \right] du \, dv \, dw$$

$$\nabla \cdot F = \left[ \frac{\partial}{\partial u}(\cdot) + \frac{\partial}{\partial v}(\cdot) + \frac{\partial}{\partial w}(\cdot) \right] |J| = H_u H_v H_w$$

如 $(u, v, w) = (r, \theta, \phi)$，则

$$\nabla \cdot F = \frac{1}{r^2 \sin\theta} \left[ \frac{\partial}{\partial r}(r^2 \sin\theta \, F_r) + \frac{\partial}{\partial \theta}(\sin\theta \, F_\theta) + \frac{\partial}{\partial \phi}(r \, F_\phi) \right]$$

## 旋度

$$\text{rot} \, \mathbf{a} = \lim_{S \to 0} \frac{\oint \mathbf{a} \cdot d\mathbf{s}}{S} = \nabla \times \mathbf{a} = \mathbf{e}_u (\cdots) + \mathbf{e}_v (\cdots) + \mathbf{e}_w (\cdots)$$

考虑 $\text{rot} \, \mathbf{a}$ 在 $u$ 轴上的投影，取 $\mathbf{n}$ 为正方向，$S$ 面是 $u = \text{常数}$，曲面 $S$ 中的曲线 $L$ 设为 $M_1 M_2 N_2 N_1$。

$$\int_{M_1 M_2} \mathbf{a} \cdot d\mathbf{s} = a(u, v, w) \cdot d\mathbf{s} = a(u, v, w) \cdot H_v \, dv = a_v (v, w) H_v (u, v, w) \, dv$$

$$N_1 (u, v + dv, w + dw), \quad N_2 (u, v + dv, w)$$

$$(g_1, g_2, g_3) \quad (g_1, g_2 + d g_2, g_3) \quad (u, v, w) M_1 \quad M_2 (u, v + dv, w)$$

$$\int_{M_2 N_2} \mathbf{a} \cdot d\mathbf{s} = a(u, v + dv, w) \cdot d\mathbf{s} = a(u, v + dv, w) \cdot H_w \, dw = a_w (u, v + dv, w) H_w (u, v + dv, w) \, dw$$

$$\int_{N_2 N_1} \mathbf{a} \cdot d\mathbf{s} = a(u, v, w + dw) \cdot d\mathbf{s} = -a(u, v, w + dw) \cdot H_v \, dv = -a_v (u, v, w + dw) H_v (u, v, w + dw) \, dv$$

$$\int_{N_1 M_1} \mathbf{a} \cdot d\mathbf{s} = -a(u, v, w) \cdot H_w \, dw = -a_w (u, v, w) H_w (u, v, w) \, dw$$

则

$$\oint \mathbf{a} \cdot d\mathbf{s} = \left[ \frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v) \right] dv \, dw = (\text{rot} \, \mathbf{a})_u \, dv \, dw \cdot H_v H_w$$

$$(\text{rot} \, \mathbf{a})_u = \frac{1}{H_v H_w} \left[ \frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v) \right]$$

$$H_u \mathbf{e}_u, \quad H_v \mathbf{e}_v, \quad H_w \mathbf{e}_w$$

$$\text{rot} \, \mathbf{a} = \frac{1}{H_u H_v H_w} \begin{vmatrix} H_u \mathbf{e}_u & H_v \mathbf{e}_v & H_w \mathbf{e}_w \\ \frac{\partial}{\partial u} & \frac{\partial}{\partial v} & \frac{\partial}{\partial w} \\ H_u a_u & H_v a_v & H_w a_w \end{vmatrix}$$

## 简单塞曼效应

于是有

\[
\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right)+\left[\frac{2\mu}{\hbar^2}\left(E-V-\frac{\hbar^2 l(l+1)}{2\mu r^2}\right)\right]R(r)=0
\]

其中 \(V\) 为势能，\(l\) 为轨道角动量量子数。

无外加电磁场时，$A=0$，$H = \frac{p^2}{2\mu} + V(r)$，$V(r) = -\frac{k}{r} - \lambda k \frac{1}{r^2}$。

加入磁场 $B = B e_z$，$H' = \frac{1}{2\mu}\left(p - qA\right)^2 + V + q\Phi$（后证）。

电荷为 $q$，质量为 $\mu$ 的粒子在矢势 $A$ 和标势 $\Phi$ 中，有 $H = \frac{1}{2\mu}\left(p - qA\right)^2 + V + q\Phi$。

选 $A = \frac{B}{2}(-y, x, 0)$，则 $H = \frac{1}{2\mu}\left[\left(p_x + \frac{qB}{2}y\right)^2 + \left(p_y - \frac{qB}{2}x\right)^2 + p_z^2\right] + V(r)$。

展开：$\frac{1}{2\mu}\left[p^2 + \frac{qB}{2}(x p_y - y p_x) + \frac{q^2 B^2}{4}(x^2 + y^2)\right] + V(r)$，其中 $\rho^2 = x^2 + y^2$，$L_z = x p_y - y p_x$。

$A_{lm} = E_{lm} \psi_{lm}(r, \theta, \phi) = R_l(r) Y_{lm}(\theta, \phi)$。

则 $\left[-\frac{\hbar^2}{2\mu}\left(\frac{1}{r^2}\frac{d}{dr}r^2\frac{d}{dr} - \frac{l(l+1)}{r^2}\right) + V(r)\right] R_l(r) Y_{lm}(\theta, \phi) = E R_l(r) Y_{lm}(\theta, \phi)$。

于是有 $\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}(E - V) - \frac{l(l+1)}{r^2}\right]R = 0$。

**注意**：① 左式 $= \left[\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right) - \frac{l(l+1)}{r^2}\right] R(r) Y_{lm}(\theta, \phi) = E R(r) Y_{lm}(\theta, \phi)$。

$-\frac{\hbar^2}{2\mu}\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right)\right] Y_{lm} - \frac{\hbar^2}{2\mu}\frac{l(l+1)}{r^2} R Y_{lm} + V(r) R Y_{lm} = E R Y_{lm}$。

$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}(E - V) - \frac{l(l+1)}{r^2}\right]R = 0$。

令 $E_0 = E - \omega_L m \hbar = E - m\hbar\omega_L$，代入 $\lambda V(r) = -\frac{k}{r} - \lambda k \frac{1}{r^2}$。

则 $\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) - \left[-\frac{2\mu}{\hbar^2}\left(-\frac{k}{r} - \lambda k \frac{1}{r^2}\right) - \frac{2\mu}{\hbar^2}(\omega_L m - E)\right]R = 0$。

$\frac{d^2R}{dr^2} + \frac{2}{r}\frac{dR}{dr} + \left[E_0 + \frac{2\mu k}{\hbar^2 r} + \frac{2\mu \lambda k}{\hbar^2 r^2} - \frac{l(l+1)}{r^2}\right]R(r) = 0$，对比碱金属原子方程，有 $E_0 = -\frac{\mu k^2}{2\hbar^2 n^2}$，$l' = l - \Delta_l$。

$$\left\{\begin{aligned} &E_{nlm} = E_0 + m\hbar\omega_L \\ &E_0 = -\frac{\mu k^2}{2\hbar^2 n^2} \end{aligned}\right.$$

$B = 0$ 时，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。

$B \neq 0$ 时，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，**不简并**。