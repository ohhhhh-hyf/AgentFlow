概率密度角度分布在 $(\theta, \varphi)$ 方向的立体角 $d\Omega$ 中电子的概率为  
$$|Y_{lm}(\theta, \varphi)|^2 d\Omega = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$$

关于径向概率分布：  
$$P(r) = r^2 R_{nl}^2(r) \, dr$$

关于概率密度角度分布：
$$P(\theta, \theta+d\theta; \varphi, \varphi+d\varphi) = \int |\psi|^2 r^2 \sin\theta \, d\theta \, d\varphi \, dr = |Y_{lm}(\theta, \varphi)|^2 \sin\theta \, d\theta \, d\varphi$$

**电流分布与磁矩**
电流密度 = 电荷 × 概率流密度
$$j = (-e) \cdot \frac{i\hbar}{2m} (\psi^* \nabla \psi - \psi \nabla \psi^*)$$

其中 $\psi_{nlm}(r, \theta, \varphi) = R_{nl}(r) P_l^m(\cos\theta) e^{im\varphi}$，$P_l^m(\cos\theta)$ 为实函数，则 $j_r = 0$。

$$j_\varphi = \frac{e\hbar m}{m r \sin\theta} |\psi|^2$$

**磁矩**  
围绕 $z$ 轴的许多环形电流（在 $x$-$y$ 平面），  
$$d\mu = dI \times S$$

其中 $S = \pi (r\sin\theta)^2$，  
$$dI = j_\varphi \times (r d\theta) \times dr$$

截面面积：$(r d\theta) \times dr$，电流 $dI = j_\varphi \times r d\theta \, dr$。

## 碱金属原子

碱金属原子的势场与氢原子不同，其径向方程为：

$$V(r)=-\frac{e^2}{r}$$

（碱金属原子）$a_{0}=$（氢原子）

$$\left[\frac{d^2}{dr^2}+\frac{2\mu}{\hbar^2}\left(E+\frac{e^2}{r}\right)-\frac{l(l+1)}{r^2}\right]R_l(r)=0 \quad \text{(径向方程)}$$

令 $l(l+1)-2\lambda=l'(l'+1)$，则类比氢原子：

$$E_n=-\frac{\mu e^4}{2\hbar^2 n'^2}, \quad n=n_r+l'+1$$

$$l'=-\frac{1}{2}+\sqrt{\left(l+\frac{1}{2}\right)^2-2\lambda}=-\frac{1}{2}+\left(l+\frac{1}{2}\right)\sqrt{1-\frac{2\lambda}{\left(l+\frac{1}{2}\right)^2}}$$

$l'$ 与 $l$ 有关，能级简并度为 $2l'+1$。

---

## 电磁场中电荷粒子的哈密顿量

在电磁场中，存在带电量为 $q$，质量为 $m$ 的粒子，粒子受力：

$$\mathbf{F}=q\mathbf{E}+q\mathbf{v}\times\mathbf{B}$$

由 $\nabla\cdot\mathbf{B}=0$，则引入 $\mathbf{A}$ 为矢势：

$$\mathbf{B}=\nabla\times\mathbf{A}, \quad \mathbf{E}=-\nabla\phi-\frac{\partial\mathbf{A}}{\partial t}$$

其中 $\phi$ 为电势。

$$\mathbf{A}=\begin{pmatrix} A_x \\ A_y \\ A_z \end{pmatrix}, \quad \nabla\times\mathbf{B}=\begin{pmatrix} \frac{\partial B_z}{\partial y}-\frac{\partial B_y}{\partial z} \\ \frac{\partial B_x}{\partial z}-\frac{\partial B_z}{\partial x} \\ \frac{\partial B_y}{\partial x}-\frac{\partial B_x}{\partial y} \end{pmatrix}$$

$$\mathbf{B}=\begin{pmatrix} B_x \\ B_y \\ B_z \end{pmatrix}$$

$$F_x=q\left[-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+v_y\left(\frac{\partial A_y}{\partial x}-\frac{\partial A_x}{\partial y}\right)-v_z\left(\frac{\partial A_x}{\partial z}-\frac{\partial A_z}{\partial x}\right)\right]$$

考虑 $A_x(x,y,z,t)$，则：

$$\frac{dA_x}{dt}=\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}$$

故：

$$F_x=q\left[-\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}+\frac{\partial A_x}{\partial x}\dot{x}+\frac{\partial A_x}{\partial y}\dot{y}+\frac{\partial A_x}{\partial z}\dot{z}\right]=-q\left(\frac{\partial\phi}{\partial x}-\frac{\partial A_x}{\partial t}\right)+q\frac{dA_x}{dt}$$

由 $\mathbf{F}=\frac{d}{dt}(m\mathbf{v})$，则：

$$\frac{d}{dt}(m\dot{x}+qA_x)=q\left(-\frac{\partial\phi}{\partial x}\right)+q\frac{dA_x}{dt}$$

令 $U=q(\phi-\mathbf{A}\cdot\mathbf{v})$，则：

$$\frac{\partial U}{\partial x}=-q\frac{\partial\phi}{\partial x}+q\frac{\partial A_x}{\partial x}\dot{x}, \quad \frac{\partial U}{\partial \dot{x}}=-qA_x, \quad \frac{\partial U}{\partial \dot{y}}=-qA_y, \quad \frac{\partial U}{\partial \dot{z}}=-qA_z$$

由拉格朗日方程 $\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{x}}\right)-\frac{\partial L}{\partial x}=F_x=-q\frac{\partial}{\partial x}(\phi-\mathbf{A}\cdot\mathbf{v})$：

$$T=\frac{1}{2}m\dot{x}^2$$

$$\frac{d}{dt}\left[\frac{\partial}{\partial \dot{x}}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})\right]-\frac{\partial}{\partial x}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})=0$$

$$\frac{d}{dt}\left[\frac{\partial}{\partial \dot{x}}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})\right]-\frac{\partial}{\partial x}(T-q\phi+q\mathbf{A}\cdot\mathbf{v})=0, \quad y、z \text{ 同理}$$

## 哈密顿量与坐标变换补充

哈密顿量  
$$H = -L = (m\mathbf{v} + q\mathbf{A})\cdot \mathbf{v} - \frac{1}{2}mv^2 - q(-\nabla V \cdot \mathbf{A}) = \frac{1}{2}mv^2 + q\phi = \frac{1}{2m}(\mathbf{P} - q\mathbf{A})^2 + q\phi$$

考虑系统中心力，  
$$\mathcal{L} = \frac{1}{2}m\dot{r}^2 - A(r) + \text{常数}$$

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

#### 笛卡尔坐标系中的表示

事实上，考虑  
$$\nabla u = \frac{\partial u}{\partial x} \mathbf{e}_x + \frac{\partial u}{\partial y} \mathbf{e}_y + \frac{\partial u}{\partial z} \mathbf{e}_z$$

于是有  
$$\left( \frac{\partial u}{\partial x}, \frac{\partial u}{\partial y}, \frac{\partial u}{\partial z} \right) = \left( \frac{\partial u}{\partial r}, \frac{\partial u}{\partial \theta}, \frac{\partial u}{\partial \phi} \right) \begin{pmatrix} \frac{\partial r}{\partial x} & \frac{\partial \theta}{\partial x} & \frac{\partial \phi}{\partial x} \\ \frac{\partial r}{\partial y} & \frac{\partial \theta}{\partial y} & \frac{\partial \phi}{\partial y} \\ \frac{\partial r}{\partial z} & \frac{\partial \theta}{\partial z} & \frac{\partial \phi}{\partial z} \end{pmatrix}$$

即  
$$\frac{\partial (u, v, w)}{\partial (x, y, z)} = \frac{\partial (u, v, w)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{1}{\frac{\partial (x, y, z)}{\partial (u, v, \omega)}}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (u, v, \omega)}$$

$$\frac{\partial (u, v, \omega)}{\partial (x, y, z)} = \frac{\partial (u, v, \omega)}{\partial (r, \theta, \phi)} \cdot \frac{\partial (r, \theta, \phi)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, \omega)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

$$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, ω)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

$$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, ω)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

$$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, ω)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

$$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, ω)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

$$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, ω)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

$$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, ω)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

$$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, ω)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

$$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, ω)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

$$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, ω)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

$$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (x, y, z)}$$

$$\frac{\partial (x, y, z)}{\partial (u, v, ω)} = \frac{\partial (x, y, z)}{\partial (r, θ, φ)} \cdot \frac{\partial (r, θ, φ)}{\partial (u, v, ω)}$$

\$\$\frac{\partial (u, v, ω)}{\partial (x, y, z)} = \frac{\partial (u, v, ω)}{\partial (r, θ, φ)} \cdot \frac

## 散度定理与旋度在正交曲线坐标系中的表达式

### 散度定理（高斯定理）

**散度定理**：向量场在闭合曲面上的通量，等于向量场的散度在该曲面包围区域内的体积分。

$$\oint_S \mathbf{a} \cdot d\mathbf{S} = \iiint_V (\nabla \cdot \mathbf{a}) \, dV$$

考虑一个由坐标面围成的体积元，其边长为 $H_u du$、$H_v dv$、$H_w dw$（其中 $H_u, H_v, H_w$ 为拉梅系数）。

对于平行于 $d\mathbf{u}$ 方向的两个面，其中一个面的通量为：

$$\mathbf{a}(u,v,w) \cdot (H_v H_w \, dv \, dw) \, \hat{\mathbf{e}}_u$$

两个相对面的通量之差为：

$$\frac{\partial (a_u H_v H_w)}{\partial u} du \, dv \, dw$$

同理，另外两对面的通量差分别为：

$$\frac{\partial (a_v H_w H_u)}{\partial v} du \, dv \, dw, \qquad \frac{\partial (a_w H_u H_v)}{\partial w} du \, dv \, dw$$

因此：

$$(\nabla \cdot \mathbf{a}) \, dV = (\nabla \cdot \mathbf{a}) \, H_u H_v H_w \, du \, dv \, dw = \left[ \frac{\partial (a_u H_v H_w)}{\partial u} + \frac{\partial (a_v H_w H_u)}{\partial v} + \frac{\partial (a_w H_u H_v)}{\partial w} \right] du \, dv \, dw$$

即：

$$\nabla \cdot \mathbf{a} = \frac{1}{H_u H_v H_w} \left[ \frac{\partial (a_u H_v H_w)}{\partial u} + \frac{\partial (a_v H_w H_u)}{\partial v} + \frac{\partial (a_w H_u H_v)}{\partial w} \right]$$

**特例**：若 $(u, v, w) = (r, \theta, \varphi)$（球坐标），则：

$$\nabla \cdot \mathbf{F} = \frac{1}{r^2 \sin\theta} \left[ \frac{\partial}{\partial r} (r^2 \sin\theta \, F_r) + \frac{\partial}{\partial \theta} (\sin\theta \, F_\theta) + \frac{\partial}{\partial \varphi} (r \, F_\varphi) \right]$$

$$= \frac{1}{r^2} \frac{\partial}{\partial r} (r^2 F_r) + \frac{1}{r \sin\theta} \frac{\partial}{\partial \theta} (\sin\theta \, F_\theta) + \frac{1}{r \sin\theta} \frac{\partial F_\varphi}{\partial \varphi}$$

### 旋度在正交曲线坐标系中的表达式

**旋度定义**：

$$\text{rot} \, \mathbf{a} = \lim_{S \to 0} \frac{\oint_L \mathbf{a} \cdot d\mathbf{l}}{S}$$

考虑 $\text{rot} \, \mathbf{a}$ 在 $u$ 轴上的投影。取 $\hat{\mathbf{e}}_u$ 为正方向，$S$ 面是 $u = \text{常数}$ 的曲面。曲面 $S$ 中的闭合曲线 $L$ 设为 $M_1 M_2 N_2 N_1 M_1$。

各段线积分：

$$\int_{M_1 M_2} \mathbf{a} \cdot d\mathbf{l} = a_v(u, v, w) H_v(u, v, w) \, dv$$

$$\int_{M_2 N_2} \mathbf{a} \cdot d\mathbf{l} = a_w(u, v + dv, w) H_w(u, v + dv, w) \, dw$$

$$\int_{N_2 N_1} \mathbf{a} \cdot d\mathbf{l} = -a_w(u, v, w + dw) H_w(u, v, w + dw) \, dw$$

$$\int_{N_1 M_1} \mathbf{a} \cdot d\mathbf{l} = -a_v(u, v, w) H_v(u, v, w) \, dv$$

则环量为：

$$\oint_L \mathbf{a} \cdot d\mathbf{l} = \left[ \frac{\partial (a_w H_w)}{\partial v} - \frac{\partial (a_v H_v)}{\partial w} \right] dv \, dw$$

因此：

$$(\text{rot} \, \mathbf{a})_u = \frac{1}{H_v H_w} \left[ \frac{\partial (a_w H_w)}{\partial v} - \frac{\partial (a_v H_v)}{\partial w} \right]$$

同理可得另外两个分量：

$$(\text{rot} \, \mathbf{a})_v = \frac{1}{H_w H_u} \left[ \frac{\partial (a_u H_u)}{\partial w} - \frac{\partial (a_w H_w)}{\partial u} \right]$$

$$(\text{rot} \, \mathbf{a})_w = \frac{1}{H_u H_v} \left[ \frac{\partial (a_v H_v)}{\partial u} - \frac{\partial (a_u H_u)}{\partial v} \right]$$

综合写成行列式形式：

$$\text{rot} \, \mathbf{a} = \frac{1}{H_u H_v H_w} \begin{vmatrix} H_u \hat{\mathbf{e}}_u & H_v \hat{\mathbf{e}}_v & H_w \hat{\mathbf{e}}_w \\ \frac{\partial}{\partial u} & \frac{\partial}{\partial v} & \frac{\partial}{\partial w} \\ H_u a_u & H_v a_v & H_w a_w \end{vmatrix}$$

```markdown
## 简单塞曼效应

无外加电磁场时，$A = \nabla^2 + V(n)$，$V(r) = -k^2 - \lambda k_1^2$。加入磁场 $B = B e_z$，$H' = H_0 + H'$（后证）。电荷为 $q$，质量为 $\mu$ 的粒子在矢势 $A$ 和标势 $\Phi$ 中，有：

$$
H = \frac{(p - qA)^2}{2\mu} + V + q\Phi
$$

选 $A = \frac{B}{2}(-y, x, 0)$，则：

$$
H = \frac{1}{2\mu}\left[\left(p_x + \frac{qB}{2}y\right)^2 + \left(p_y - \frac{qB}{2}x\right)^2 + p_z^2\right] + V(r)
$$

$$
H = \frac{1}{2\mu}\left[p_x^2 + p_y^2 + p_z^2\right] + \frac{qB}{2\mu}(x p_y - y p_x) + \frac{q^2 B^2}{8\mu}(x^2 + y^2) + V(r)
$$

其中 $x p_y - y p_x = L_z$，$x^2 + y^2 = \rho^2$。

$$
H = \frac{p^2}{2\mu} + \frac{qB}{2\mu} L_z + \frac{q^2 B^2}{8\mu} \rho^2 + V(r)
$$

令 $H' = \frac{qB}{2\mu} L_z + \frac{q^2 B^2}{8\mu} \rho^2$（微扰项）。

本征函数：$\psi_{nlm}(r, \theta, \phi) = R_{nl}(r) Y_{lm}(\theta, \phi)$，则：

$$
\left[-\frac{\hbar^2}{2\mu} \frac{1}{r^2} \frac{d}{dr}\left(r^2 \frac{d}{dr}\right) + \frac{\hbar^2 l(l+1)}{2\mu r^2} + V(r)\right] R_{nl}(r) = E_{nl} R_{nl}(r)
$$

**注意**：左式 = $\left[-\frac{\hbar^2}{2\mu} \frac{1}{r^2} \frac{d}{dr}\left(r^2 \frac{d}{dr}\right) + \frac{\hbar^2 l(l+1)}{2\mu r^2} + V(r)\right] R_{nl}(r) = E_{nl} R_{nl}(r)$

令 $E_0 = E - \omega_L m \hbar = E - m \hbar \omega_L$，代入 $V(r) = -k^2 - \lambda k$，则：

$$
\left[-\frac{\hbar^2}{2\mu} \frac{1}{r^2} \frac{d}{dr}\left(r^2 \frac{d}{dr}\right) + \frac{\hbar^2 l(l+1)}{2\mu r^2} - \frac{k^2}{r} - \frac{\lambda k}{r^2} - \omega_L m \hbar - E\right] R(r) = 0
$$

$$
\left[-\frac{\hbar^2}{2\mu} \frac{1}{r^2} \frac{d}{dr}\left(r^2 \frac{d}{dr}\right) + \frac{\hbar^2 l(l+1)}{2\mu r^2} + \frac{k^2}{r} + \frac{\lambda k}{r^2} + \omega_L m \hbar - E\right] R(r) = 0
$$

对比碱金属原子方程，有 $E_0 = -\frac{k^2}{2\mu} = -\frac{1}{2} \mu k^2$，$E = E_0 + m \hbar \omega_L$。

**$B=0$ 时**，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。**$B \neq 0$ 时**，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，不简并。
```