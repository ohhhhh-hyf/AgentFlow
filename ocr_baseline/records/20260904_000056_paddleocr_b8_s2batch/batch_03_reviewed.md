## 概率密度与角度分布

概率密度角度分布在 $(\theta, \varphi)$ 方向的立体角 $d\Omega$ 中电子的概率为：

$$|Y_{lm}(\theta, \varphi)|^2 d\Omega = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$$

关于径向概率分布：

$$P(r) = r^2 |R_{nl}(r)|^2 \, dr$$

关于概率密度角度分布：

$$P(\theta, \varphi; \, \theta + d\theta, \, \varphi + d\varphi) = \int |\psi|^2 r^2 \sin\theta \, dr \, d\theta \, d\varphi = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$$

## 电流分布与磁矩

电流密度 = 电荷 × 概率流密度：

$$\vec{j}_c = (-e) \cdot \frac{\hbar}{2mi} (\psi^* \nabla \psi - \psi \nabla \psi^*)$$

其中：

$$\psi_{nlm}(r, \theta, \varphi) = N R_{nl}(r) P_l^m(\cos\theta) e^{im\varphi}$$

若 $R_{nl}(r) P_l^m(\cos\theta)$ 为实函数，则：

$$\vec{j} = \frac{e\hbar m}{m_e r \sin\theta} |\psi_{nlm}|^2 \hat{e}_\varphi$$

即：

$$\vec{j} = \frac{e\hbar m}{m_e r \sin\theta} |R_{nl}(r) P_l^m(\cos\theta)|^2 \hat{e}_\varphi$$

这些电流是围绕 $z$ 轴的许多环形电流（在 $x$-$y$ 平面内），磁矩为：

$$d\vec{\mu} = dI \times \vec{S}$$

其中环形电流的截面积为：

$$dS = (r \sin\theta) \times (r \, d\theta) \times dr$$

电流为：

$$dI = j_\varphi \times r \, d\theta \, dr$$

## 碱金属原子

碱金属原子的势场与氢原子不同，其径向方程为：

$$V(r)=-\frac{e^2}{r} \quad (\text{碱金属原子})$$

$$a_0=\frac{\hbar^2}{me^2}$$

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

$$\mathbf{B}=\nabla\times\mathbf{A}, \quad \mathbf{E}=-\nabla\phi-\frac{\partial\mathbf{A}}{\partial t}$$

其中 $\phi$ 为电势。

$$\mathbf{A}=(A_x, A_y, A_z)$$

$$\nabla\times\mathbf{B}=\nabla(\nabla\cdot\mathbf{A})-\nabla^2\mathbf{A}$$

$$\mathbf{B}=(B_x, B_y, B_z)$$

$$F_x=q\left[-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+v_y\left(\frac{\partial A_y}{\partial x}-\frac{\partial A_x}{\partial y}\right)-v_z\left(\frac{\partial A_x}{\partial z}-\frac{\partial A_z}{\partial x}\right)\right]$$

考虑 $A_x(x,y,z,t)$，则：

$$\frac{dA_x}{dt}=\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}$$

故：

$$F_x=q\left[-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+\frac{\partial}{\partial x}(\mathbf{v}\cdot\mathbf{A})-\frac{dA_x}{dt}\right]=q\left(-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+\frac{\partial}{\partial x}(\mathbf{v}\cdot\mathbf{A})-\frac{dA_x}{dt}\right)$$

由 $\mathbf{F}=\frac{d}{dt}(m\mathbf{v})$，则：

$$\frac{d}{dt}(m\dot{x}+qA_x)=q\left(-\frac{\partial\phi}{\partial x}+\frac{\partial}{\partial x}(\mathbf{v}\cdot\mathbf{A})\right)$$

令 $U=q(\phi-\mathbf{A}\cdot\mathbf{v})$，则：

$$\frac{\partial U}{\partial x}=q\frac{\partial\phi}{\partial x}-q\frac{\partial}{\partial x}(\mathbf{A}\cdot\mathbf{v})$$

$$\frac{\partial U}{\partial \dot{x}}=-qA_x, \quad \frac{\partial U}{\partial \dot{y}}=-qA_y, \quad \frac{\partial U}{\partial \dot{z}}=-qA_z$$

由拉格朗日方程：

$$\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{x}}\right)-\frac{\partial L}{\partial x}=F_x=-q\frac{\partial}{\partial x}(\phi-\mathbf{A}\cdot\mathbf{v})$$

$$T=\frac{1}{2}m\dot{x}^2$$

$$\frac{d}{dt}\left(\frac{\partial}{\partial \dot{x}}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})\right)-\frac{\partial}{\partial x}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})=0$$

对 $y$、$z$ 同理。

$$\frac{d}{dt}(m\dot{x}+qA_x)$$

## 哈密顿量

哈密顿量 $H = -L = (m\mathbf{v} + q\mathbf{A}) \cdot \mathbf{v} - \frac{1}{2}mv^2 - (-V + \mathbf{A} \cdot \mathbf{v}) = \frac{1}{2}mv^2 + q\varphi = \frac{1}{2m}(\mathbf{P} - q\mathbf{A})^2 + q\varphi$

考虑系统中心力场，$H = \frac{1}{2m}\mathbf{P}^2 - \frac{A^2}{2m} + V(r)$

## 补充：坐标系变换

### 典型空间中的度规

二维空间，线元 $ds^2 = (dx)^2 + (dy)^2 = (dx, dy) \begin{pmatrix} dx \\ dy \end{pmatrix} = g_{ij} dx^i dx^j$

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

$$\left( \frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z} \right) = \left( \frac{\partial u}{\partial r}, \frac{\partial u}{\partial \theta}, \frac{\partial u}{\partial \varphi} \right) \frac{\partial (x, y, z)}{\partial (r, \theta, \varphi)}$$

$$\frac{\partial (u, v, w)}{\partial (x, y, z)} = \frac{\partial (u, v, w)}{\partial (r, \theta, \varphi)} \cdot \frac{\partial (r, \theta, \varphi)}{\partial (x, y, z)}$$

即 $\frac{\partial (u, v, w)}{\partial (x, y, z)} = \frac{\partial (u, v, w)}{\partial (r, \theta, \varphi)} \cdot \frac{\partial (r, \theta, \varphi)}{\partial (x, y, z)}$

## 散度

向量场在闭合曲面的通量等于向量场的散度在曲面包围区域的体积分。

设 $F = P\mathbf{e}_u + Q\mathbf{e}_v + R\mathbf{e}_w$，考虑平行于 $d$ 的四个面，在剩下两面中一个面的通量为：

两个面的通量之差为 $\left(\frac{\partial}{\partial u}(F \cdot H_v H_w)\right) du \, dv \, dw = \frac{\partial}{\partial u}(F_u H_v H_w) \, du \, dv \, dw$

同理，另外两个通量差为 $\frac{\partial}{\partial v}(F_v H_w H_u) \, du \, dv \, dw$，$\frac{\partial}{\partial w}(F_w H_u H_v) \, du \, dv \, dw$。

$$\therefore (\nabla \cdot F) \, dV = (\nabla \cdot F) J \, du \, dv \, dw = \left[\frac{\partial}{\partial u}(F_u H_v H_w) + \frac{\partial}{\partial v}(F_v H_w H_u) + \frac{\partial}{\partial w}(F_w H_u H_v)\right] du \, dv \, dw$$

$$\nabla \cdot F = \frac{1}{J}\left[\frac{\partial}{\partial u}(F_u H_v H_w) + \frac{\partial}{\partial v}(F_v H_w H_u) + \frac{\partial}{\partial w}(F_w H_u H_v)\right] = \frac{1}{H_u H_v H_w}\left[\frac{\partial}{\partial u}(F_u H_v H_w) + \frac{\partial}{\partial v}(F_v H_w H_u) + \frac{\partial}{\partial w}(F_w H_u H_v)\right]$$

如 $(u, v, w) = (r, \theta, \phi)$，则

$$\nabla \cdot F = \frac{1}{r^2 \sin\theta}\left[\frac{\partial}{\partial r}(r^2 \sin\theta \, F_r) + \frac{\partial}{\partial \theta}(\sin\theta \, F_\theta) + \frac{\partial}{\partial \phi}(r F_\phi)\right] = \frac{1}{r^2}\frac{\partial}{\partial r}(r^2 F_r) + \frac{1}{r\sin\theta}\frac{\partial}{\partial \theta}(\sin\theta \, F_\theta) + \frac{1}{r\sin\theta}\frac{\partial F_\phi}{\partial \phi}$$

## 旋度

$$\text{rot}\, \mathbf{a} = \lim_{S \to 0} \frac{\oint \mathbf{a} \cdot d\mathbf{l}}{S}$$

考虑 $\text{rot}\, \mathbf{a}$ 在 $u$ 轴上的投影，取 $\mathbf{n}$ 为正方向，$S$ 面是 $u = \text{常数}$，曲面 $S$ 中的曲线 $L$ 设为 $M_1 M_2 N_2 N_1$。

$$\int_{M_1 M_2} \mathbf{a} \cdot d\mathbf{l} = a(u, v, w) \cdot d\mathbf{l} = a(u, v, w) \cdot H_v \, dv = a_v(u, v, w) H_v(u, v, w) \, dv$$

其中 $M_1 = (u, v, w)$，$M_2 = (u, v + dv, w)$，$N_1 = (u, v, w + dw)$，$N_2 = (u, v + dv, w + dw)$。

$$\int_{M_2 N_2} \mathbf{a} \cdot d\mathbf{l} = a(u, v + dv, w) \cdot d\mathbf{l} = a(u, v + dv, w) \cdot H_w \, dw = a_w(u, v + dv, w) H_w(u, v + dv, w) \, dw$$

$$\int_{N_2 N_1} \mathbf{a} \cdot d\mathbf{l} = a(u, v, w + dw) \cdot d\mathbf{l} = -a(u, v, w + dw) \cdot H_v \, dv = -a_v(u, v, w + dw) H_v(u, v, w + dw) \, dv$$

$$\int_{N_1 M_1} \mathbf{a} \cdot d\mathbf{l} = -a(u, v, w) \cdot H_w \, dw = -a_w(u, v, w) H_w(u, v, w) \, dw$$

则

$$\oint \mathbf{a} \cdot d\mathbf{l} = \left[\frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v)\right] dv \, dw = (\text{rot}\, \mathbf{a})_u \, dv \, dw = \frac{1}{H_v H_w}\left[\frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v)\right] H_v H_w \, dv \, dw$$

$$(\text{rot}\, \mathbf{a})_u = \frac{1}{H_v H_w}\left[\frac{\partial}{\partial v}(a_w H_w) - \frac{\partial}{\partial w}(a_v H_v)\right]$$

$$\text{rot}\, \mathbf{a} = \frac{1}{H_u H_v H_w} \begin{vmatrix} H_u \mathbf{e}_u & H_v \mathbf{e}_v & H_w \mathbf{e}_w \\ \frac{\partial}{\partial u} & \frac{\partial}{\partial v} & \frac{\partial}{\partial w} \\ H_u a_u & H_v a_v & H_w a_w \end{vmatrix}$$

## 简单塞曼效应

于是有

\[
\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right)+\left[\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{r}\right)-\frac{l(l+1)}{r^2}\right]R(r)=0
\]

其中 $E_0=-\frac{\mu e^4}{2\hbar^2}$，$B=0$ 时能级简并度为 $2l+1$。

无外加电磁场时，$A=0$，$H = \frac{p^2}{2\mu} + V(r)$，$V(r) = -\frac{k}{r} - \lambda k \frac{1}{r^2}$。

加入磁场 $B = B e_z$，$H' = H_0 + H'$（$H'$ 后证）。

电荷为 $q$，质量为 $\mu$ 的粒子在矢势 $A$ 和标势 $\Phi$ 中，有
$$H = \frac{(p - qA)^2}{2\mu} + V + q\Phi$$

选 $A = \frac{B}{2}(-y, x, 0)$，则
$$H = \frac{1}{2\mu}\left[\left(p_x + \frac{qB}{2}y\right)^2 + \left(p_y - \frac{qB}{2}x\right)^2 + p_z^2\right] + V(r)$$

展开得
$$\frac{1}{2\mu}\left[p^2 + \frac{qB}{2}(x p_y - y p_x) + \frac{q^2 B^2}{4}(x^2 + y^2)\right] + V(r)$$

其中 $L_z = x p_y - y p_x$，$\rho^2 = x^2 + y^2$。

$$H \psi_{nlm} = E_{nlm} \psi_{nlm}(r, \theta, \phi) = R_{nl}(r) Y_{lm}(\theta, \phi)$$

则
$$\left[-\frac{\hbar^2}{2\mu}\left(\frac{1}{r^2}\frac{d}{dr}r^2\frac{d}{dr} - \frac{l(l+1)}{r^2}\right) + \frac{qB}{2\mu}L_z + \frac{q^2B^2}{8\mu}\rho^2 + V(r)\right] R Y = E R Y$$

于是有
$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}(E - V) - \frac{l(l+1)}{r^2} - \frac{qB}{\hbar}m - \frac{q^2B^2}{4\hbar^2}\rho^2\right]R = 0$$

**注意**：① 左式 $= \frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) - \frac{l(l+1)}{r^2}R + \left[\frac{2\mu}{\hbar^2}(E - V) - \frac{qB}{\hbar}m\right]R = 0$

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) - \frac{l(l+1)}{r^2}R + \left[\frac{2\mu}{\hbar^2}(E - V) - \frac{qB}{\hbar}m\right]R = E R$$

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}(E - V) - \frac{l(l+1)}{r^2} - \frac{qB}{\hbar}m\right]R = 0$$

令 $E_0 = E - \omega_L m\hbar$，$E = E_0 + \omega_L m\hbar$，代入 $\lambda V(r) = -\frac{k}{r} - \lambda k \frac{1}{r^2}$：

则
$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) - \left[\frac{2\mu}{\hbar^2}\left(-\frac{k}{r} - \lambda k\frac{1}{r^2}\right) - \frac{l(l+1)}{r^2} - \frac{2\mu}{\hbar^2}(\omega_L m\hbar - E)\right]R = 0$$

$$\frac{d^2R}{dr^2} + \frac{2}{r}\frac{dR}{dr} + \left[\frac{2\mu}{\hbar^2}\left(E_0 + \frac{k}{r}\right) - \frac{l(l+1) - 2\mu\lambda k/\hbar^2}{r^2}\right]R = 0$$

对比碱金属原子方程，有 $E_0 = -\frac{\mu k^2}{2\hbar^2 n^2}$，$l' = l - \Delta_l$。

$$\{ + m\hbar \omega_L \}$$

$B = 0$ 时，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。

$B \neq 0$ 时，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，**不简并**。