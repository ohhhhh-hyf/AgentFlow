# 概率密度角度分布与电流分布、磁矩

## 概率密度角度分布

在 $(0,4)$ 方向的立体角 $d\Omega$ 中电子的概率为：

$$|Y_{lm}(\theta,\phi)|^2 d\Omega = |Y_{lm}(\theta,\phi)|^2 \sin\theta\, d\theta\, d\phi$$

其中：

$$Y_{lm}(\theta,\phi) = \Theta_{lm}(\theta) \Phi_m(\phi) = P_l^m(\cos\theta) \cdot e^{im\phi}$$

$$|Y_{lm}(\theta,\phi)|^2 d\Omega \propto [P_l^m(\cos\theta)]^2 d\Omega$$

**只与 $l, m$ 有关。**

### 关于径向概率分布

$$P(r_0, r_0 + dr) = \int r^2 \sin\theta\, d\theta\, d\phi\, dr \cdot |R_{nl}(r)|^2 = r_0^2 dr \left[ \int |Y_{lm}|^2 \sin\theta\, d\theta\, d\phi \right]$$

### 关于概率密度角度分布

$$P(\theta \to \theta + d\theta;\ \phi \to \phi + d\phi) = \int r^2 \sin\theta\, d\theta\, d\phi\, dr \cdot |Y_{lm}(\theta,\phi)|^2 = |Y_{lm}(\theta,\phi)|^2 \sin\theta\, d\theta\, d\phi$$

## 电流分布与磁矩

缺失行中混有 OCR 噪声（如 `d(rsmo)xd(rose)` 和 `截面面积：(rdo)xdr 电流＝Jepxrdodr`），无法构成完整语义，且与前后文（电流分布与磁矩、量子化结论）不连贯，故不输出。

电流密度 = 电荷 × 概率流密度：

$$\mathbf{j} = (-e) \cdot \frac{i\hbar}{2m} (\psi^* \nabla \psi - \psi \nabla \psi^*)$$

其中梯度算符：

$$\nabla = \hat{e}_r \frac{\partial}{\partial r} + \hat{e}_\theta \frac{1}{r} \frac{\partial}{\partial \theta} + \hat{e}_\phi \frac{1}{r \sin\theta} \frac{\partial}{\partial \phi}$$

波函数：

$$\psi_{nlm}(r,\theta,\phi) = N_{nl} R_{nl}(r) P_l^m(\cos\theta) e^{im\phi}$$

其中 $R_{nl}(r)$、$P_l^m(\cos\theta)$ 为实函数，则 $\frac{\partial \psi}{\partial r} = \frac{\partial \psi}{\partial \theta} = 0$。

角向电流密度：

$$j_\phi = \frac{i\hbar}{2m} \left[ \psi^* \frac{1}{r\sin\theta} \frac{\partial \psi}{\partial \phi} - \psi \frac{1}{r\sin\theta} \frac{\partial \psi^*}{\partial \phi} \right] = \frac{\hbar m}{m_e r \sin\theta} |\psi|^2$$

**这些是围绕 Z 轴的许多环形电流（在 $x$-$y$ 平面内）。**

$$dM = dI \times S$$

总磁矩：

$$\mathbf{M} = \int [\pi (r\sin\theta)^2 j_\phi r\, d\theta\, dr] \cdot \hat{e}_z = \int \left[ -\frac{e\hbar m}{2m_e} r^2 \sin\theta\, dr\, d\theta \right] \hat{e}_z$$

其中：

- 截面面积：$(r\, d\theta) \times dr$
- 电流：$j_\phi \times r\, d\theta\, dr$

$$M_z = -\frac{e\hbar}{2m_e} m = -\mu_B m$$

$M_z$ 为常量，**磁矩在 Z 方向的投影是量子化的**。

碱金属原子
V(r)＝一，k、＝研忘（氢原子） V(r)=-5F﹣水器（碱金属原子）a0=
()+［张（E++x)-]R(r)=0（径向方程）
＝卞（)+[(+)--2]R1(H)=0.
令l(1+1)-2x=('(1'+1)，则类比氢原子，Ent＝一·本，n=nr+l'+1
('=﹣支＋(1+3)2-2>=-1/2+(l+1)、1﹣与l有关，能级简并度为2l+1.
电磁场中电荷粒子的哈密顿量
在电磁场中，存在带电量为q，质量为M的粒子，粒子受力户＝qE+qvxB
电势
由v.B=0，则引入A，为失势，B=DXA,E=-D4-{(V.B=p,PxE=-
ijk
B=マx及＝=(-)+（张﹣张）+(﹣琦）R
|Ax Ay Az
=[(-)-(-)]+［之（-)-x（数﹣骑）］子
VxB=
+[x(-)-4(2奇﹣碧）]R
BxByBz
Fx=q[﹣張﹣號＋y(﹣奇）-（张﹣張）]
考虑Ax(x,y,z,t)，则＝號＋歲·x＋鄂·g＋發·2,
故Fx=q[﹣張﹣+x職＋1發＋張］=﹣最9(4-V·R)-9
锟＝户，则我（mx+qAx)=q(﹣强）+qV．器
令U=q(4-A·V)，则＝=-=-qAx,=-9Ay,=-9A2
由拉格朗日方程：我（聂）﹣聂＝Fx=-q录（4-A·D)-q袋
T=1mv2
>（颢＋qA)-(T-94+9A·7)=0=>(aT-+-0)-(T-94+qA)=0,y.Z同理．
L=T-U=±mV2-q(4-V.A）为拉格朗日量． 正则动量P=taex=mv+qA

哈密顿量 $H = \mathbf{P} \cdot \mathbf{V} - L = (m\mathbf{v} + q\mathbf{A}) \cdot \mathbf{V} - \left[ \frac{1}{2}mv^2 - q(\phi - \mathbf{V} \cdot \mathbf{A}) \right] = \frac{1}{2}mv^2 + q\phi = \frac{1}{2m}(\mathbf{P} - q\mathbf{A})^2 + q\phi$

考虑系统中心力场，$\mathbf{A} = \frac{1}{2}\mathbf{B} \times \mathbf{r}$，$H = \frac{1}{2m}(\mathbf{P} - q\mathbf{A})^2 + q\phi$

## 补充：坐标系变换

对标量函数 $U(q_1, q_2, q_3)$，在 $q$ 增长方向的梯度 $(\nabla U)_{q_i} = \frac{\partial U}{\partial q_i} = \frac{1}{h_i} \frac{\partial U}{\partial q_i}$。

于是有 $\left( \frac{\partial U}{\partial q_1}, \frac{\partial U}{\partial q_2}, \frac{\partial U}{\partial q_3} \right)$。

### 典型空间中的度规

二维空间，线元 $ds^2 = (dx)^2 + (dy)^2 = (dx \ dy) \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix} \begin{pmatrix} dx \\ dy \end{pmatrix} = \sum_{i,j} g_{ij} dx^i dx^j$

$g_{ij}$ 即 $\begin{pmatrix} g_{11} & g_{12} \\ g_{21} & g_{22} \end{pmatrix}$ 第 $i$ 行第 $j$ 列元素，是二维欧氏空间的度规在直角坐标 $\{x^1, x^2\} = \{x, y\}$ 下的形式。

若取极坐标系 $\{r, \phi\}$，$x = r\cos\phi$，$y = r\sin\phi$，则 $ds^2 = (dr\cos\phi - r\sin\phi \, d\phi)^2 + (dr\sin\phi + r\cos\phi \, d\phi)^2 = (dr)^2 + r^2(d\phi)^2$

$ds^2 = \sum_{i,j} g_{ij} dx^i dx^j$，$G = \begin{pmatrix} 1 & 0 \\ 0 & r^2 \end{pmatrix}$。

三维欧氏空间，线元 $ds^2 = (dx)^2 + (dy)^2 + (dz)^2 = \sum_{i,j} g_{ij} dx^i dx^j$，$G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$

若取球坐标，即 $\{x^1, x^2, x^3\} = \{r, \theta, \phi\}$，$x = r\sin\theta\cos\phi$，$y = r\sin\theta\sin\phi$，$z = r\cos\theta$

$ds^2 = \sum_{i,j} g_{ij} dx^i dx^j$，$G = \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2\sin^2\theta \end{pmatrix}$

$ds^2 = (dr \ d\theta \ d\phi) \begin{pmatrix} 1 & 0 & 0 \\ 0 & r^2 & 0 \\ 0 & 0 & r^2\sin^2\theta \end{pmatrix} \begin{pmatrix} dr \\ d\theta \\ d\phi \end{pmatrix}$

### 梯度算子

对于正交曲线坐标系，度规矩阵 $G$ 一定为对角矩阵，记作 $\text{diag}(h_1^2, h_2^2, h_3^2)$，即（$ds^2$ 后）

$h_i = \sqrt{\left(\frac{\partial x}{\partial q_i}\right)^2 + \left(\frac{\partial y}{\partial q_i}\right)^2 + \left(\frac{\partial z}{\partial q_i}\right)^2}$，在 $q_2, q_3$ 不变而 $q_1$ 相差微小变量时，线元 $(ds_1)^2 = h_1^2 (dq_1)^2$（正交系 $(q_1, q_2, q_3)$）。

对标量函数 $U(q_1, q_2, q_3)$，在 $q_1$ 增长方向的梯度 $(\nabla U)_{q_1} = \frac{\partial U}{\partial s_1} = \frac{1}{h_1} \frac{\partial U}{\partial q_1}$。

### 张量在笛卡尔坐标系中的表示

事实上，考虑 $\nabla U = \mathbf{F}$，$\mathbf{F} = F_u \mathbf{e}_u + F_v \mathbf{e}_v + F_w \mathbf{e}_w$，$\nabla U = \left(\frac{\partial U}{\partial x}\right) \mathbf{e}_x + \left(\frac{\partial U}{\partial y}\right) \mathbf{e}_y + \left(\frac{\partial U}{\partial z}\right) \mathbf{e}_z$

于是有 $\left(\frac{\partial U}{\partial x}, \frac{\partial U}{\partial y}, \frac{\partial U}{\partial z}\right)$

$\left(\frac{\partial U}{\partial x}, \frac{\partial U}{\partial y}, \frac{\partial U}{\partial z}\right) = \left(\frac{\partial U}{\partial u}, \frac{\partial U}{\partial v}, \frac{\partial U}{\partial w}\right) \begin{pmatrix} \frac{\partial u}{\partial x} & \frac{\partial u}{\partial y} & \frac{\partial u}{\partial z} \\ \frac{\partial v}{\partial x} & \frac{\partial v}{\partial y} & \frac{\partial v}{\partial z} \\ \frac{\partial w}{\partial x} & \frac{\partial w}{\partial y} & \frac{\partial w}{\partial z} \end{pmatrix}$

$\left(\frac{\partial U}{\partial u}, \frac{\partial U}{\partial v}, \frac{\partial U}{\partial w}\right) = \left(\frac{\partial U}{\partial x}, \frac{\partial U}{\partial y}, \frac{\partial U}{\partial z}\right) \begin{pmatrix} \frac{\partial x}{\partial u} & \frac{\partial x}{\partial v} & \frac{\partial x}{\partial w} \\ \frac{\partial y}{\partial u} & \frac{\partial y}{\partial v} & \frac{\partial y}{\partial w} \\ \frac{\partial z}{\partial u} & \frac{\partial z}{\partial v} & \frac{\partial z}{\partial w} \end{pmatrix}$

对于正交曲线坐标系，$\mathbf{e}_i = \frac{1}{h_i} \frac{\partial \mathbf{r}}{\partial q_i}$，即 $d(u,v,w)$

$\left(\frac{\partial U}{\partial u}, \frac{\partial U}{\partial v}, \frac{\partial U}{\partial w}\right) = \left(\frac{\partial U}{\partial x}, \frac{\partial U}{\partial y}, \frac{\partial U}{\partial z}\right) \frac{\partial (x,y,z)}{\partial (u,v,w)}$

于是 $\nabla U = \frac{1}{h_1} \frac{\partial U}{\partial u} \mathbf{e}_u + \frac{1}{h_2} \frac{\partial U}{\partial v} \mathbf{e}_v + \frac{1}{h_3} \frac{\partial U}{\partial w} \mathbf{e}_w$

### ③ 散度

向量场在闭合曲面的通量等于向量场的散度在曲面包围区域的体积分。

考虑以 $du, dv, dw$ 为边的平行六面体 $dV$，$F = F_u e_u + F_v e_v + F_w e_w$。

$dV$ 的体积为 $\| \frac{\partial (x,y,z)}{\partial (u,v,w)} \| \, du \, dv \, dw = |J| \, du \, dv \, dw$。

平行于 $dv$ 的四个面，在剩下两面中一个面的通量为 $F \cdot n \, dS$。

两个面的通量之差为 $\frac{\partial}{\partial v} (F_v |J| \, du \, dw) \, dv = \frac{\partial}{\partial v} (F_v |J|) \, du \, dv \, dw$。

同理，另外两个通量差为 $\frac{\partial}{\partial w} (F_w |J|) \, du \, dv \, dw$，$\frac{\partial}{\partial u} (F_u |J|) \, du \, dv \, dw$。

由 $\oint (F \cdot n) \, dS = (\nabla \cdot F) \, dV = (\nabla \cdot F) |J| \, du \, dv \, dw = \left[ \frac{\partial}{\partial u} (F_u |J|) + \frac{\partial}{\partial v} (F_v |J|) + \frac{\partial}{\partial w} (F_w |J|) \right] du \, dv \, dw$。

因此：
$$
\nabla \cdot F = \frac{1}{|J|} \left[ \frac{\partial}{\partial u} (F_u |J|) + \frac{\partial}{\partial v} (F_v |J|) + \frac{\partial}{\partial w} (F_w |J|) \right] = \frac{1}{H_u H_v H_w} \left[ \frac{\partial}{\partial u} (F_u H_v H_w) + \frac{\partial}{\partial v} (F_v H_u H_w) + \frac{\partial}{\partial w} (F_w H_u H_v) \right]
$$

若 $(u,v,w) = (r, \theta, \phi)$，则 $\nabla \cdot F = \frac{1}{r^2 \sin \theta} \left[ \frac{\partial}{\partial r} (r^2 \sin \theta \, F_r) + \frac{\partial}{\partial \theta} (r^2 \sin \theta \, F_\theta) + \frac{\partial}{\partial \phi} (r^2 \sin \theta \, F_\phi) \right]$。

---

### ④ 旋度

$\operatorname{rot} \mathbf{a} = \lim \dots$

$\mathbf{a} = a_u e_u + a_v e_v + a_w e_w$

考虑 $\operatorname{rot} \mathbf{a}$ 在 $u$ 轴上的投影，取 $n$ 为正方向，$S$ 面是 $u = \text{常数}$。曲面 $S$ 中的曲线 $L$ 设为 $M_1 M_2 N_2 N_1$。

$\oint_{M_1 N_1} \mathbf{a} \cdot d\mathbf{s} = \mathbf{a}(u,v,w) \cdot d\mathbf{s} = \mathbf{a}(u,v,w) \cdot H_v e_v \, dv = a_v(u,v,w) H_v(u,v,w) \, dv$

$\oint_{N_2 M_2} \mathbf{a} \cdot d\mathbf{s} = a_2(u, v+dv, w) \cdot d\mathbf{s} = \mathbf{a}(u, v+dv, w) \cdot H_w e_w \, dw = a_w(u, v+dv, w) H_w(u, v+dv, w) \, dw$

$\oint_{N_2 N_1} \mathbf{a} \cdot d\mathbf{s} = \mathbf{a}(u, v, w+dw) \cdot d\mathbf{s} = -\mathbf{a}(u, v, w+dw) \cdot H_v e_v \, dv = -a_v(u, v, w+dw) H_v(u, v, w+dw) \, dv$

$\oint_{M_1 M_2} \mathbf{a} \cdot d\mathbf{s} = -\mathbf{a}(u, v, w) \cdot H_w e_w \, dw = -a_w(u, v, w) H_w(u, v, w) \, dw$

$\oint \mathbf{a} \cdot d\mathbf{s} = \frac{\partial (a_w H_w)}{\partial v} \, dv \, dw - \frac{\partial (a_v H_v)}{\partial w} \, dv \, dw = \left[ \frac{\partial (a_w H_w)}{\partial v} - \frac{\partial (a_v H_v)}{\partial w} \right] dv \, dw$

则 $(\operatorname{rot} \mathbf{a})_u = \frac{1}{H_v H_w} \left[ \frac{\partial (a_w H_w)}{\partial v} - \frac{\partial (a_v H_v)}{\partial w} \right]$

同理：
$$
(\operatorname{rot} \mathbf{a})_v = \frac{1}{H_u H_w} \left[ \frac{\partial (a_u H_u)}{\partial w} - \frac{\partial (a_w H_w)}{\partial u} \right]
$$

$$
\operatorname{rot} \mathbf{a} = \frac{1}{H_u H_v H_w} \begin{vmatrix} H_u e_u & H_v e_v & H_w e_w \\ \frac{\partial}{\partial u} & \frac{\partial}{\partial v} & \frac{\partial}{\partial w} \\ H_u a_u & H_v a_v & H_w a_w \end{vmatrix}
$$

# 简单塞曼效应

华中科技大学  
UNIVERSITY OF SCIENCE AND TECHNOLOGY

无外加电磁场时，$A_0 = P + V(r)$，$V(r) = -kF - \lambda K$。

加入磁场 $\mathbf{B} = B\mathbf{e}_z$，$A' = \frac{1}{2}\mathbf{B} \times \mathbf{r}$，$A = A_0 + A'$（后证）。

电荷为 $q$，质量为 $m$ 的粒子在矢势 $A$ 和标势 $\phi$ 中，有 $H = \frac{1}{2m}|\mathbf{p} - q\mathbf{A}|^2 + V + q\phi$。

对塞曼效应，$\phi = 0$，$V(r) = -\frac{k}{r} - \frac{\lambda}{r^2}$，磁场 $\mathbf{B} = \nabla \times \mathbf{A} = B\mathbf{e}_z$，$q = -e$，$\nabla \cdot \mathbf{A} = 0$ 满足库仑规范。

选 $\mathbf{A} = \left(-\frac{1}{2}By, \frac{1}{2}Bx, 0\right)$，则

$$H = \frac{1}{2m}\left[\left(p_x + \frac{eB}{2}y\right)^2 + \left(p_y - \frac{eB}{2}x\right)^2 + p_z^2\right] + V(r)$$

$$H = \frac{p^2}{2m} + \frac{eB}{2m}(xp_y - yp_x) + \frac{e^2B^2}{8m}(x^2 + y^2) + V(r)$$

令 $\omega_L = \frac{eB}{2m}$，$\rho^2 = x^2 + y^2$，又 $L_z = xp_y - yp_x$，则

$$H = \frac{p^2}{2m} + \omega_L L_z + \frac{1}{2}m\omega_L^2 \rho^2 + V(r)$$

$\omega_L^2 \rho^2 \ll \omega_L$，可忽略 $\Rightarrow H = \frac{p^2}{2m} + \omega_L L_z + V(r) = H_0 + H'$

$$H\psi_{nlm} = E_{nlm}\psi_{nlm}(r,\theta,\phi) = R_{nl}(r)Y_{lm}(\theta,\phi)$$

则

$$-\frac{\hbar^2}{2m}\left[\frac{1}{r^2}\frac{\partial}{\partial r}\left(r^2\frac{\partial}{\partial r}\right) + \frac{1}{r^2\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial}{\partial\theta}\right) + \frac{1}{r^2\sin^2\theta}\frac{\partial^2}{\partial\phi^2}\right]R(r)Y(\theta,\phi) + V(r)R(r)Y + \omega_L m\hbar R(r)Y = E R(r)Y$$

于是有

$$\left[-\frac{\hbar^2}{2m}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right) + \frac{l(l+1)\hbar^2}{2mr^2} + V(r)\right]R(r)Y(\theta,\phi) = (E - \omega_L m\hbar)R(r)Y(\theta,\phi)$$

**注意**：左式 $= \left[-\frac{\hbar^2}{2m}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{d}{dr}\right) - \frac{\hbar^2}{2mr^2}\left(\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2}{\partial\phi^2}\right) + V(r)\right]R(r)Y(\theta,\phi) = ER(r)Y(\theta,\phi)$

$$-\frac{\hbar^2}{2m}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right)Y(\theta,\phi) - \frac{\hbar^2}{2mr^2}R(r)\left[\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial Y}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2 Y}{\partial\phi^2}\right] + V(r)R(r)Y(\theta,\phi) - \omega_L m\hbar R(r)Y - ER(r)Y(\theta,\phi) = 0$$

$$\Rightarrow -\frac{\hbar^2}{2m}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + V(r) - E = \frac{\hbar^2}{2mr^2}\left[\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2}{\partial\phi^2}\right]$$

令 $E_0 = E - \omega_L m\hbar = E - m\hbar\omega_L$，代入 $V(r) = -\frac{k}{r} - \frac{\lambda}{r^2}$，则

$$-\frac{\hbar^2}{2m}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) - \frac{\lambda}{r^2}R - \frac{k}{r}R - \frac{\hbar^2}{2mr^2}l(l+1)R - (E_0 - m\hbar\omega_L) = 0$$

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \frac{2m}{\hbar^2}\left(E_0 + \frac{k}{r} - \frac{\lambda'}{r^2}\right)R(r) = 0$$

对比碱金属原子方程，有 $E_0 = -\frac{\hbar^2}{2m a^2} = -\frac{me^4}{2\hbar^2 n'^2}$。

$$n = n_r + l' + 1, \quad l'(l'+1) = l(l+1) - 2\lambda, \quad E = E_0 + m\hbar\omega_L = E_{nlm} = -\frac{me^4}{2\hbar^2 n^2} + m\hbar\omega_L$$

$B = 0$ 时，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。

$B \neq 0$ 时，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，不简并。

1张张弱
于是有（船，船，船）

(awHw)_x(avHu)

2muHw)_3(awHwl

1HuQu HvQyHwaw