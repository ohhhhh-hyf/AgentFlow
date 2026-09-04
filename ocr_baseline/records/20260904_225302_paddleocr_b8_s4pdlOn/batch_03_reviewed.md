```markdown
概率密度角度分布在 $(\theta, \varphi)$ 方向的立体角 $d\Omega$ 中电子的概率为 $|Y_{lm}(\theta, \varphi)|^2 d\Omega = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$。

关于径向概率分布：$P(r) = r^2 R_{nl}^2(r) \, dr$。

关于概率密度角度分布：$P(\theta, \theta+d\theta; \varphi, \varphi+d\varphi) = \int |\psi|^2 r^2 \sin\theta \, dr \, d\theta \, d\varphi = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$。

**电流分布与磁矩**  
电流密度 = 电荷 × 概率流密度  
$j = (-e) \cdot \frac{i\hbar}{2m} (\psi^* \nabla \psi - \psi \nabla \psi^*)$  
其中 $\psi_{nlm}(r, \theta, \varphi) = R_{nl}(r) P_l^m(\cos\theta) e^{im\varphi}$，$P_l^m(\cos\theta)$ 为实函数，则 $j_r = 0$。

$j_\varphi = \frac{\hbar m}{m_e r \sin\theta} |\psi|^2$  
这是围绕 $z$ 轴的许多环形电流（在 $x$-$y$ 平面），$d\mu = dI \times S$。

其中 $S = \pi (r\sin\theta)^2$，$dI = j_\varphi \cdot (r d\theta) \times dr$。

截面面积：$(r d\theta) \times dr$，电流 $dI = j_\varphi \times r d\theta \, dr$。
```

```markdown
# 碱金属原子

$$V(r)=-\frac{e^2}{r}$$（氢原子）  
$$V(r)=-\frac{e^2}{r}$$（碱金属原子）  
$$a_0=\frac{\hbar^2}{me^2}$$

$$\left[\frac{d^2}{dr^2}+\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{r}\right)-\frac{l(l+1)}{r^2}\right]R_l(r)=0$$（径向方程）

令 $l(l+1)-2\lambda=l(l+1)$，则类比氢原子，$E_n=-\frac{e^2}{2a_0 n^2}$，$n=n_r+l+1$，$l=-\frac{1}{2}+\sqrt{(l+\frac{1}{2})^2-2\lambda}$，$E_n$ 与 $l$ 有关，能级简并度为 $2l+1$。

---

# 电磁场中电荷粒子的哈密顿量

在电磁场中，存在带电量为 $q$，质量为 $m$ 的粒子，粒子受力 $\mathbf{F}=q\mathbf{E}+q\mathbf{v}\times\mathbf{B}$。

由 $\nabla\cdot\mathbf{B}=0$，则引入 $\mathbf{A}$ 为矢势，$\mathbf{B}=\nabla\times\mathbf{A}$，$\mathbf{E}=-\nabla\phi-\frac{\partial \mathbf{A}}{\partial t}$（电势）。

$$\mathbf{A}=\begin{pmatrix} A_x \\ A_y \\ A_z \end{pmatrix}, \quad \nabla\times\mathbf{B}=\begin{pmatrix} \frac{\partial B_z}{\partial y}-\frac{\partial B_y}{\partial z} \\ \frac{\partial B_x}{\partial z}-\frac{\partial B_z}{\partial x} \\ \frac{\partial B_y}{\partial x}-\frac{\partial B_x}{\partial y} \end{pmatrix}$$

$$\mathbf{B}=\begin{pmatrix} B_x \\ B_y \\ B_z \end{pmatrix}, \quad F_x=q\left[-\frac{\partial \phi}{\partial x}-\frac{\partial A_x}{\partial t}+v_y\left(\frac{\partial A_y}{\partial x}-\frac{\partial A_x}{\partial y}\right)-v_z\left(\frac{\partial A_x}{\partial z}-\frac{\partial A_z}{\partial x}\right)\right]$$

考虑 $A_x(x,y,z,t)$，则 $\frac{dA_x}{dt}=\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}$。

故 $F_x=q\left[-\frac{\partial \phi}{\partial x}-\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}\right]=-q\left(\frac{\partial \phi}{\partial x}-\frac{\partial \mathbf{A}}{\partial t}\cdot\nabla\right)$

由 $\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{x}}\right)=F_x$，则 $\frac{d}{dt}(m\dot{x}+qA_x)=q\left(-\frac{\partial \phi}{\partial x}\right)+q\dot{x}\frac{\partial A_x}{\partial x}$。

令 $U=q(\phi-\mathbf{A}\cdot\mathbf{v})$，则 $\frac{\partial U}{\partial x}=-q\frac{\partial \phi}{\partial x}+q\frac{\partial A_x}{\partial t}$，$\frac{\partial U}{\partial \dot{x}}=-qA_x$，$\frac{\partial U}{\partial \dot{y}}=-qA_y$，$\frac{\partial U}{\partial \dot{z}}=-qA_z$。

由拉格朗日方程：$\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{x}}\right)-\frac{\partial L}{\partial x}=F_x=-q\frac{\partial}{\partial x}(\phi-\mathbf{A}\cdot\mathbf{v})$，$T=\frac{1}{2}m\dot{x}^2$。

$$\frac{d}{dt}\left(\frac{\partial}{\partial \dot{x}}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})\right)-\frac{\partial}{\partial x}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})=0$$，$y$、$z$ 同理。
```

## 哈密顿量与坐标变换补充

哈密顿量  
$$H = -L = (m\mathbf{v} + q\mathbf{A}) \cdot \mathbf{v} - \frac{1}{2}mv^2 - q(-\nabla V \cdot \mathbf{A}) = \frac{1}{2}mv^2 + q\phi = \frac{1}{2m}(\mathbf{P} - q\mathbf{A})^2 + q\phi$$

考虑系统中心力，  
$$\mathcal{L} = \frac{1}{2}m\dot{r}^2 - A(r) + 0 + \dots$$

---

## 补充：坐标系变换

### 典型空间中的度规

**二维空间**，线元  
$$ds^2 = (dx)^2 + (dy)^2 = (dx\ dy) \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix} \begin{pmatrix} dx \\ dy \end{pmatrix} = g_{ij} dx^i dx^j$$

若取极坐标系 $(r, \phi)$，$x = r\cos\phi$，$y = r\sin\phi$，则  
$$ds^2 = (dr\cos\phi - r\sin\phi\, d\phi)^2 + (dr\sin\phi + r\cos\phi\, d\phi)^2 = dr^2 + r^2 d\phi^2$$  
$$ds^2 = g_{ij} dx^i dx^j, \quad G = \begin{pmatrix} 1 & 0 \\ 0 & r^2 \end{pmatrix}$$

**三维欧氏空间**，线元  
$$ds^2 = (dx)^2 + (dy)^2 + (dz)^2 = \delta_{ij} dx^i dx^j, \quad \delta = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$$

若取球坐标，即 $\{x^1, x^2, x^3\} = \{r, \theta, \phi\}$，  
$$x = r\sin\theta\cos\phi, \quad y = r\sin\theta\sin\phi, \quad z = r\cos\theta$$

度规张量为  
$$G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2\sin^2\theta \end{pmatrix}$$

---

### 梯度算子

$$h_i = \sqrt{g_{ii}} = \left( \frac{\partial x}{\partial q^i} \right)^2 + \left( \frac{\partial y}{\partial q^i} \right)^2 + \left( \frac{\partial z}{\partial q^i} \right)^2$$

在 $q_2, q_3$ 不变而 $q_1$ 相差微小变量时，线元  
$$(ds)^2 = h_1^2 (dq^1)^2 \quad (\text{正交曲线坐标})$$

对标量函数 $u(q_1, q_2, q_3)$，在增长方向的梯度  
$$(\nabla u)_i = \frac{1}{h_i} \frac{\partial u}{\partial q^i} \mathbf{e}_i$$

**笛卡尔坐标系中的表示**

事实上，考虑  
$$\nabla u = \frac{\partial u}{\partial x} \mathbf{e}_x + \frac{\partial u}{\partial y} \mathbf{e}_y + \frac{\partial u}{\partial z} \mathbf{e}_z$$

于是有  
$$\left( \frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z} \right) = \left( \frac{\partial u}{\partial r}, \frac{\partial u}{\partial \theta}, \frac{\partial u}{\partial \phi} \right) \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

又  
$$\left( \frac{\partial u}{\partial r}, \frac{\partial u}{\partial \theta}, \frac{\partial u}{\partial \phi} \right) = \left( \frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z} \right) \cdot \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)}$$

即  
$$\frac{\partial (u, v, w)}{\partial (x, y, z)} = \frac{\partial (u, v, w)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (u, v, w)}{\partial (r, \theta, \phi)} = \frac{\partial (u, v, w)}{\partial (x, y, z)} \cdot \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, w)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, w)}$$

$$\frac{\partial (u, v, w)}{\partial (x, y, z)} = \frac{1}{\frac{\partial (x, y, z)}{\partial (u, v, w)}}$$

## 散度定理与正交曲线坐标系中的旋度

### 散度定理（高斯定理）

**散度定理**：向量场在闭合曲面上的通量，等于向量场的散度在该曲面包围区域内的体积分。

$$\oint_S \mathbf{a} \cdot d\mathbf{S} = \iiint_V (\nabla \cdot \mathbf{a}) \, dV$$

### 正交曲线坐标系中的散度

考虑正交曲线坐标系 $(u, v, w)$，拉梅系数为 $H_u, H_v, H_w$，体积元为 $dV = H_u H_v H_w \, du \, dv \, dw$。

考虑向量场 $\mathbf{a}$ 在 $u$ 方向的分量 $a_u$。取一个由坐标面围成的微小六面体，其中两个面垂直于 $u$ 方向。平行于 $d$ 的四个面（即 $u$ 为常数的两个面），在剩下两面中一个面的通量为：

$$a_u H_v H_w \, dv \, dw$$

两个面的通量之差为：

$$\frac{\partial (a_u H_v H_w)}{\partial u} du \, dv \, dw = \frac{\partial (a_u H_v H_w)}{\partial u} \frac{dV}{H_u H_v H_w} \cdot H_u H_v H_w \, du \, dv \, dw$$

同理，另外两个方向的通量差分别为：

$$\frac{\partial (a_v H_w H_u)}{\partial v} du \, dv \, dw, \qquad \frac{\partial (a_w H_u H_v)}{\partial w} du \, dv \, dw$$

因此：

$$\nabla \cdot \mathbf{a} = \frac{1}{H_u H_v H_w} \left[ \frac{\partial (a_u H_v H_w)}{\partial u} + \frac{\partial (a_v H_w H_u)}{\partial v} + \frac{\partial (a_w H_u H_v)}{\partial w} \right]$$

即：

$$\nabla \cdot \mathbf{a} = \frac{1}{H_u H_v H_w} \left[ \frac{\partial}{\partial u}(a_u H_v H_w) + \frac{\partial}{\partial v}(a_v H_w H_u) + \frac{\partial}{\partial w}(a_w H_u H_v) \right]$$

**特例**：若 $(u, v, w) = (r, \theta, \phi)$（球坐标），则 $H_r = 1$，$H_\theta = r$，$H_\phi = r \sin\theta$，于是：

$$\nabla \cdot \mathbf{a} = \frac{1}{r^2 \sin\theta} \left[ \frac{\partial}{\partial r}(r^2 \sin\theta \, a_r) + \frac{\partial}{\partial \theta}(\sin\theta \, a_\theta) + \frac{\partial}{\partial \phi}\left(\frac{r}{\sin\theta} a_\phi\right) \right]$$

即：

$$\nabla \cdot \mathbf{a} = \frac{1}{r^2}\frac{\partial}{\partial r}(r^2 a_r) + \frac{1}{r \sin\theta}\frac{\partial}{\partial \theta}(\sin\theta \, a_\theta) + \frac{1}{r \sin\theta}\frac{\partial a_\phi}{\partial \phi}$$

### 旋度

$$\text{rot} \, \mathbf{a} = \lim_{S \to 0} \frac{\oint_L \mathbf{a} \cdot d\mathbf{l}}{S}$$

考虑 $\text{rot} \, \mathbf{a}$ 在 $u$ 轴上的投影。取 $n$ 为正方向，$S$ 面是 $u = \text{常数}$ 的曲面，曲面 $S$ 中的曲线 $L$ 设为 $M M_2 N_2 N_1 M$。

沿 $M M_2$：$\mathbf{a} \cdot d\mathbf{l} = a(u, v, w) \cdot H_v \, dv = a_v(u, v, w) H_v(u, v, w) \, dv$

沿 $M_2 N_2$：$\mathbf{a} \cdot d\mathbf{l} = a(u, v+dv, w) \cdot H_w \, dw = a_w(u, v+dv, w) H_w(u, v+dv, w) \, dw$

沿 $N_2 N_1$：$\mathbf{a} \cdot d\mathbf{l} = -a(u, v, w+dw) \cdot H_v \, dv = -a_v(u, v, w+dw) H_v(u, v, w+dw) \, dv$

沿 $N_1 M$：$\mathbf{a} \cdot d\mathbf{l} = -a(u, v, w) \cdot H_w \, dw = -a_w(u, v, w) H_w(u, v, w) \, dw$

则：

$$\oint_L \mathbf{a} \cdot d\mathbf{l} = \frac{\partial (a_w H_w)}{\partial v} dv \, dw - \frac{\partial (a_v H_v)}{\partial w} dv \, dw = \left[ \frac{\partial (a_w H_w)}{\partial v} - \frac{\partial (a_v H_v)}{\partial w} \right] dv \, dw$$

因此：

$$(\text{rot} \, \mathbf{a})_u = \frac{1}{H_v H_w} \left[ \frac{\partial (a_w H_w)}{\partial v} - \frac{\partial (a_v H_v)}{\partial w} \right]$$

同理可得另外两个分量：

$$(\text{rot} \, \mathbf{a})_v = \frac{1}{H_w H_u} \left[ \frac{\partial (a_u H_u)}{\partial w} - \frac{\partial (a_w H_w)}{\partial u} \right]$$

$$(\text{rot} \, \mathbf{a})_w = \frac{1}{H_u H_v} \left[ \frac{\partial (a_v H_v)}{\partial u} - \frac{\partial (a_u H_u)}{\partial v} \right]$$

综合写成行列式形式：

$$\text{rot} \, \mathbf{a} = \frac{1}{H_u H_v H_w} \begin{vmatrix} H_u \hat{e}_u & H_v \hat{e}_v & H_w \hat{e}_w \\ \frac{\partial}{\partial u} & \frac{\partial}{\partial v} & \frac{\partial}{\partial w} \\ H_u a_u & H_v a_v & H_w a_w \end{vmatrix}$$

```markdown
## 简单塞曼效应

无外加电磁场时，$A = \nabla^2 + V(n)$，$V(r) = -k^2 - \lambda k_1^2$。加入磁场 $B = B e_z$，$H' = H_0 + H'$（后证）。电荷为 $q$，质量为 $\mu$ 的粒子在矢势 $A$ 和标势 $\Phi$ 中，有

$$
H = \frac{(p - qA)^2}{2\mu} + V + q\Phi
$$

选 $A = \frac{B}{2}(-y, x, 0)$，则

$$
H = \frac{1}{2\mu}\left[\left(p_x + \frac{qB}{2}y\right)^2 + \left(p_y - \frac{qB}{2}x\right)^2 + p_z^2\right] + V(r)
$$

$$
H = \frac{1}{2\mu}\left[p_x^2 + p_y^2 + p_z^2 + \frac{qB}{2}(x p_y - y p_x) + \frac{q^2 B^2}{4}(x^2 + y^2)\right] + V(r)
$$

其中 $\rho^2 = x^2 + y^2$，$L_z = x p_y - y p_x$。

---

设 $A_{lm} = E_{lm} \psi_{lm}(r, \theta, \phi) = R_l(r) Y_{lm}(\theta, \phi)$，则

$$
\left[-\frac{\hbar^2}{2\mu}\left(\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{d}{dr}\right) - \frac{l(l+1)}{r^2}\right) + V(r)\right] R_l(r) Y_{lm} = E R_l(r) Y_{lm}
$$

于是有

$$
-\frac{\hbar^2}{2\mu}\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right)\right] + \frac{\hbar^2 l(l+1)}{2\mu r^2} R + V(r) R = E R
$$

**注意**：左式 $= \left[-\frac{\hbar^2}{2\mu}\left(\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{d}{dr}\right)\right) + \frac{\hbar^2 l(l+1)}{2\mu r^2} + V(r)\right] R(r) = E R(r)$

即

$$
-\frac{\hbar^2}{2\mu}\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right)\right] + \left[\frac{\hbar^2 l(l+1)}{2\mu r^2} + V(r) - E\right] R(r) = 0
$$

---

令 $E_0 = E - \omega_L m \hbar = E - m \hbar \omega_L$，代入 $V(r) = -k^2 - \lambda k$，则

$$
-\frac{\hbar^2}{2\mu}\left[\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right)\right] + \left[\frac{\hbar^2 l(l+1)}{2\mu r^2} - \frac{k^2}{r} - \frac{\lambda k}{r^2} - (E_0 + m \hbar \omega_L)\right] R(r) = 0
$$

整理得

$$
\frac{1}{r^2}\frac{d}{dr}\left(r^2 \frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}\left(E_0 + \frac{k^2}{r} + \frac{\lambda k}{r^2}\right) - \frac{l(l+1)}{r^2}\right] R(r) = 0
$$

对比碱金属原子方程，有

$$
E_0 = -\frac{\mu k^2}{2\hbar^2 n^2} = -\frac{R}{n^2}, \quad \omega_L = \frac{qB}{2\mu}
$$

**当 $B = 0$ 时**，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。  
**当 $B \neq 0$ 时**，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，不简并。
```