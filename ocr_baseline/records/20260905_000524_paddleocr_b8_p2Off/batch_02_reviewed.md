# 简单塞曼效应

无外加电磁场时，$A=²+V(r)$，$V(r）=-k²-λk/r$

加入磁场 $B=Be_z$，$H'=A_0+H'$（后证）

电荷为 $q$，质量为 $\mu$ 的粒子在矢势 $A$ 和标势中，有 $H=\frac{(P-qA)^2}{2\mu}+V+q\Phi$

选 $A=\frac{B}{2}(-y,x,0)$，则 $H=\frac{1}{2\mu}[(p_x+\frac{qB}{2}y)^2+(p_y-\frac{qB}{2}x)^2]+V(r)$

$H=\frac{1}{2\mu}(p_x^2+p_y^2)+\frac{qB}{2\mu}L_z+\frac{q^2B^2}{8\mu}(x^2+y^2)+V(r)$，$\rho^2=x^2+y^2$

$\psi_{nlm}=E_{nlm}\psi_{nlm}(r,\theta,\phi)=R_{nl}(r)Y_{lm}(\theta,\phi)$

则 $\frac{1}{r^2}\frac{d}{dr}(r^2\frac{dR}{dr})+[\frac{2\mu}{\hbar^2}(E-V)-\frac{l(l+1)}{r^2}]R=0$

于是有 $\frac{1}{r^2}\frac{d}{dr}(r^2\frac{dR}{dr})+\frac{2\mu}{\hbar^2}[E-V(r)]R=0$

**注意** ①左式 $=\frac{1}{r^2}\frac{d}{dr}(r^2\frac{dR}{dr})+[\frac{2\mu}{\hbar^2}(E-V)-\frac{l(l+1)}{r^2}]R=0$

$-\frac{1}{r^2}\frac{d}{dr}(r^2\frac{dR}{dr})+\frac{l(l+1)}{r^2}R-\frac{2\mu}{\hbar^2}(E-V)R=0$

$\frac{1}{r^2}\frac{d}{dr}(r^2\frac{dR}{dr})+[\frac{2\mu}{\hbar^2}(E-V)-\frac{l(l+1)}{r^2}]R=0$

令 $E_0=E-\omega_L m\hbar=E-m$，代 $\lambda V(r)=-k-\lambda k$

则 $\frac{1}{r^2}\frac{d}{dr}(r^2\frac{dR}{dr})-[\frac{2\mu}{\hbar^2}(-\frac{k}{r}-\lambda k)-\frac{l(l+1)}{r^2}]R=0$

$\frac{d^2R}{dr^2}+\frac{2}{r}\frac{dR}{dr}+[\frac{2\mu}{\hbar^2}(E_0+\frac{k}{r})-\frac{l(l+1)}{r^2}]R=0$，对比碱金属原子方程，有 $E_0=-\frac{\mu k^2}{2\hbar^2 n^2}$

$\{+m$

$B=0$ 时，能级简并度为 $2l+1$，即一个能级对应 $(2l+1)$ 个量子态。

$B≠0$ 时，原本的能级分裂为 $(2l+1)$ 个，一个能级对应一个量子态，**不简并**。

# 理想气体的微观模型与压强

## 标准状态与分子数密度

标准状态下的气体分子数密度 $n_0 = \frac{p_0}{kT_0}$，表示每 $\text{m}^3$ 理想气体中的微观粒子数。

分子线度为 $d$，则 $a \cdot p \cdot N_A = M \cdot d$，即可不计分子本身的大小。

## 理想气体的微观模型

① 可不计分子本身的大小

② 除碰撞外，气体分子间及气体分子同器壁间的相互作用可忽略

③ 分子在两次碰撞间做匀速直线运动

## 压强的微观模型

① 宏观上认为器壁受连续作用力

② 热平衡时，假设分子和器壁的碰撞是弹性碰撞

③ 分子混沌性假设：平衡态时，气体分子的热运动速度无择优方向

设第 $i$ 个分子与 $A$ 面碰撞，$y$ 方向分量不变，$x$ 方向速度分量由 $v_{ix}$ 变为 $-v_{ix}$。

$$P = \frac{2mv_x}{t} \times \frac{N}{bc} = \frac{Nmv_x^2}{abc}$$

$$v^2 = v_x^2 + v_y^2 + v_z^2, \quad \overline{v_x^2} = \frac{1}{3}\overline{v^2}$$

$\overline{E_k} = \frac{1}{2}m\overline{v^2}$ 为粒子的平均动能。

$$\therefore P = \frac{2}{3}n\overline{E_k} = nkT \Rightarrow \overline{E_k} = \frac{3}{2}kT$$

## 分子的平均动能与理想气体系统的内能

只考虑分子平动动能，$U = N\overline{E_k} = \frac{3}{2}NkT = \frac{3}{2}RT$

定体热容 $C_V = \left(\frac{\partial U}{\partial T}\right)_V = \frac{3}{2}R$，$C_{V,m} = \frac{3}{2}R$。

# 近独立粒子系的麦克斯韦—玻尔兹曼分布能量分布律

## 微观粒子基本运动状态的经典描述（能量、坐标、动量）

### ① 自由平动粒子

在三维空间中运动时，粒子的自由度为 3，位置由 $x、y、z$ 标定，与之共轭的动量为 $P_{x}=m\dot{x}$，$P_{y}=m\dot{y}$，$P_{z}=m\dot{z}$，$\dot{x}$ 表示 $x$ 对时间的导数。

无外力作用时 $E=\frac{1}{2m}(P_{x}^{2}+P_{y}^{2}+P_{z}^{2})$。粒子状态可由 $x、y、z，P_{x}、P_{y}、P_{z}$ 确定。

### ② 线性谐振子

质量为 $m$ 的粒子在弹性力 $F=-kx$ 作用下在平衡点附近作简谐运动，振动圆频率 $\omega=\sqrt{\frac{k}{m}}$。

$E=\frac{P^{2}}{2m}+\frac{1}{2}m\omega^{2}x^{2}$ → $\frac{P^{2}}{2m\varepsilon}+\frac{x^{2}}{2\varepsilon/(m\omega^{2})}=1$

以 $x、P$ 为直角坐标可构成二维 $\mu$ 空间，若 $\varepsilon$ 给定，则代表点的轨迹是椭圆，椭圆面积 $=\pi\sqrt{\frac{2\varepsilon}{m\omega^{2}}}\cdot\sqrt{2m\varepsilon}$，即 $S=\frac{2\pi\varepsilon}{\omega}$。

### ③ 转子（双原子分子整体刚性转动）

考虑质量为 $m$ 的质点 $A$ 被具有一定长度的轻杆系于原点时所做运动（$r$ 一定）：

$E=\frac{1}{2}m(\dot{x}^{2}+\dot{y}^{2}+\dot{z}^{2})$，$x=r\sin\theta\cos\varphi$，$y=r\sin\theta\sin\varphi$，$z=r\cos\theta$

$E=\frac{1}{2}m(r^{2}\dot{\theta}^{2}+r^{2}\sin^{2}\theta\dot{\varphi}^{2})$

对于双原子分子，两质点绕系统质心转动可约化为质量为 $\mu$ 的单体转动问题。

## 转子转动能量与动量

设 $I_{总}=m_{1}r_{1}^{2}+m_{2}r_{2}^{2}=\mu r^{2}$，系统转动能量 $T=\frac{1}{2}m_{1}r_{1}^{2}(\dot{\theta}^{2}+\sin^{2}\theta\dot{\varphi}^{2})+\frac{1}{2}m_{2}r_{2}^{2}(\dot{\theta}^{2}+\sin^{2}\theta\dot{\varphi}^{2})$

即 $T=\frac{1}{2}\mu r^{2}(\dot{\theta}^{2}+\sin^{2}\theta\dot{\varphi}^{2})=\frac{1}{2\mu r^{2}}\left(P_{\theta}^{2}+\frac{P_{\varphi}^{2}}{\sin^{2}\theta}\right)$

$P_{\theta}=\mu r^{2}\dot{\theta}=P_{\theta 1}+P_{\theta 2}$，$P_{\varphi}=\mu r^{2}\sin^{2}\theta\dot{\varphi}$（与 $\theta、\varphi$ 共轭的动量）

$T_{总}=\frac{1}{2}\mu r^{2}\dot{\theta}^{2}+\frac{1}{2}\mu r^{2}\sin^{2}\theta\dot{\varphi}^{2}=\frac{1}{2\mu r^{2}}\left(P_{\theta}^{2}+\frac{P_{\varphi}^{2}}{\sin^{2}\theta}\right)$

## 宏观分布、组态、微观态

### μ空间分割（宏观）

把 $\mu$ 空间分成许多小体元 $\Delta \mu_j$（$j=1,2,\cdots,l$），大小适当，足够小到可近似认为代表点落在 $\Delta \mu_j$ 内的粒子运动状态相同，但也不是无穷小，要满足 $\Delta \mu_j \ge 10$（统计需要）。

### 宏观分布与宏观态（与 $\mu$ 空间的分布 $\{a_j\}$ 对应）

宏观状态参量是相应微观物理量的统计平均值。知道了 $\Delta \mu_j$（$j=1,2,\cdots,l$）体元内代表点的数目 $a_j$（$j=1,2,\cdots,l$），即可确定系统的内能等宏观量的平均值，从而系统的宏观态也就确定了。

### 宏观分布的组态（配容）（哪些粒子的代表点在 $\Delta \mu_j$ 内）

经典力学中，粒子是可分辨的，交换两粒子的状态会改变系统的状态（微观）。一个宏观分布 $\{a_j\}$ 对应的组态数 $W = \dfrac{N!}{\prod_j a_j!}$，即将 $N$ 个粒子按 $\{a_j\}$ 分布给 $l$ 个状态的可能数。

### 经典力学中一个组态的微观数（相字 $\Delta \mu_j$ → 相格 $h^r$，过渡到微观）

粒子的状态是连续的，粒子和系统的微观运动状态不可数，人为划出最小的格子。将 $p, q$ 分为等间隔区域，$\delta p \delta q = h_0$，$(\delta q_1 p_1) \cdots (\delta q_r p_r) = h_0$，相格 $h_0$ 代表一个粒子态。子相字空间小体元 $\Delta \mu_j$（$j=1,2,\cdots,l$）中粒子运动状态数为 $\Delta \omega_j = \dfrac{\Delta \mu_j}{h_0}$，$a_j$ 个粒子在 $\Delta \omega_j$ 个运动状态上分布的可能微观状态数为 $\dfrac{(\Delta \omega_j)^{a_j}}{a_j!}$，多个粒子可以处于同一相格内。

### 一个分布的微观分布数

$$W = N! \prod_{j=1}^{l} \frac{(\Delta \omega_j)^{a_j}}{a_j!}$$

## 等概率原理和最概然统计

若系统的各微观态无更多限制，就假定一切符合所有约束条件的微观态出现的概率相等。

**最概然统计**：认为出现概率最大（即微观态数最多）的那个宏观态分布对应于系统的平衡态。

## 最概然分布求算

由斯特林公式，$M$ 足够大时，有 $\ln M! \approx M\ln M - M$

则 $\delta(\ln a! - \ln a_j!) = (\ln a + 1 - \ln a_j - 1)\delta a_j = (\ln a - \ln a_j)\delta a_j = 0$

又有粒子数和能量守恒条件（孤立），则 $\sum \delta a_j = 0$，$\sum E_j \delta a_j = 0$。

令 $f(a_1, a_2, \cdots, a_j, \alpha, \beta) = \sum(\ln a - \ln a_j)\delta a_j + \alpha(\sum a_j - N) + \beta(\sum E_j a_j - E)$

则 $f$ 取极值时，$\frac{\partial f}{\partial a_j} = 0$，即 $-\ln a_j + \alpha + \beta E_j = 0$。

$a_j = e^{-\alpha - \beta E_j}$，且此时 $f$ 取极大值。

$\beta = \frac{1}{kT}$，是一个普遍量，$a_j = \Delta \mu_j e^{-\beta E_j}$

$\alpha$ 由 $\sum a_j = N$ 确定，即 $\frac{e^{-\alpha}}{\sum e^{-\beta E_j}} = \frac{N}{\sum e^{-\beta E_j}}$

---

**宏观态 $\{a_j\}$ 可继续细分**：一种分布有多种实现方法（多个组态）；$\mu$ 空间的分布一个组态有多种微观态。

## △M的分割举例

一维线性谐振子 $E=\frac{p^2}{2m}+\frac{1}{2}m\omega^2 x^2$，$E=$ 常数，代表点的轨迹为椭圆（μ空间）。

$S=\pi ab=\pi\sqrt{2mE}\cdot\sqrt{\frac{2E}{m\omega^2}}=\frac{2\pi E}{\omega}$，当 $\Delta E=h\nu$ 时，$\Delta S=h$。

偏离最概然分布的概率很小，平衡态对应的微观态数为 $W$，最概然分布附近一个分布对应的微观态数为 $W'$。假设 $N=2n$ 个粒子处在一个体积 $V$ 的空间中，将 $V$ 等体积划分为 $\Delta M_1, \Delta M_2, \dots$

$$W'=\frac{(2n)!}{n!n!}\cdot\frac{n!}{(n+\Delta n)!(n-\Delta n)!}=\frac{(2n)!}{(n+\Delta n)!(n-\Delta n)!}$$

$n$ 很大，$\frac{\Delta n}{n}\to 0$。

## 量子态中的μ空间

$\Delta x\Delta p_x\ge h$，一个粒子的代表不再是点，而是一团“小空间”，粒子的状态是分立的，不再需要用“μ空间”，只需考虑分立能级上的分布即可。

刚性转子能级 $E=\frac{l(l+1)\hbar^2}{2I}$，$A=\frac{\hbar^2}{2I}$，$\varepsilon_l=l(l+1)A$。

谐振子能级 $$E=\left(n+\frac{1}{2}\right)h\nu$$

平动子能级间隔极小，可视为连续分布，按 $d\varepsilon$ 分能级；常温下，转动也可看作连续（不含 $H_2$）；**振动一般必须看作分立能级**，直接分析量子能级简并度。

## 量子态与相空间体积之间的对应关系

对于一个自由度为 $r$ 的粒子，它的 μ 空间中大小为 $h^r$ 的相体积对应一个量子态。

第一象限 $0\sim$ 范围内的总量子态数：

$$\Phi(\varepsilon)=\frac{\pi}{h^3}\left(2m\varepsilon\right)^{3/2}abc=\frac{4\pi V}{3h^3}(2m\varepsilon)^{3/2}$$

$$p_r^2=p_x^2+p_y^2+p_z^2=2m\varepsilon$$

## 经典极限条件

$e^{-\alpha}\ll 1$，即 $\frac{n_r}{g_r}\ll 1$ 时，量子统计过渡到经典统计（玻尔兹曼分布适用）。

## 算符

### 狄拉克符号

$|4\rangle$：右矢；$\langle 4|$：左矢，称 $|4\rangle$ 或 $\langle 4|$ 为态矢，$4$ 是一个标签，用于区分不同的量子态。

$\langle 4| = |4\rangle^+$，左矢与右矢是一种共轭转置关系。$\langle \alpha \varphi| = \alpha^* \langle \varphi|$（$\alpha$ 为复数）。

**内积**：$(\varphi, \psi) = \langle \varphi | \psi \rangle$。坐标表象 $-\infty$：$\int \varphi^*(r) \psi(r) \, dt$，$dt = dxdydz$ 为微体积元，$|\psi|^2 = \psi^*(x, y, z) \psi(x, y, z)$。

$\langle \varphi | \psi \rangle = \langle \psi | \varphi \rangle^*$，用定积分理解是共轭，用矩阵理解是转置后取共轭。

**正交**：$\langle \varphi | \psi \rangle = 0$ 代表 $\varphi$ 和 $\psi$ 是正交的；**归一**：$\langle \psi | \psi \rangle = 1$ 代表 $\psi$ 是归一化的。

**平均值**：力学量 $A$ 在归一化量子态 $\psi$ 下的平均值 $\bar{A} = \langle \psi | A | \psi \rangle$。

$| \psi \rangle$、$\langle \psi |$ 是量子态 $\psi$ 在右矢、左矢空间的不同表示。

### 左、右矢空间的算符运算

设 $A$ 和 $\tilde{A}$ 是两个算符，$\forall |\psi\rangle$ 和 $|\varphi\rangle$，若 $\langle \varphi | A | \psi \rangle = \langle \tilde{A} \varphi | \psi \rangle$，则称 $\tilde{A}$ 为 $A$ 的转置算符。

$= A\psi$，在右矢空间中，$|\psi\rangle = |\psi\rangle = |A\psi\rangle$，默认 $A$ 向右作用；在左矢空间中，$\langle \psi | = \langle \psi | A^\dagger$，算符 $A^{+}(A^{\dagger})$ 向左作用。$\langle \psi | A^\dagger = \langle A\psi | = \langle \psi |$。若 $A$ 为厄米算符，则 $\langle \psi | A = \langle \psi | A$。

**厄米算符在左、右矢空间中的运算具有形式不变性。**

算符在左矢和右矢之间的转换本质上是对偶空间的伴随映射。

关于 $(|A\psi\rangle)^\dagger = \langle \psi | A^\dagger$：$\bar{A} = \langle \psi | A | \psi \rangle$，$\bar{A}^* = \langle \psi | A^\dagger | \psi \rangle$，$\langle \psi | A | \psi \rangle^* = \langle \psi | A^\dagger | \psi \rangle = \langle A\psi | \psi \rangle$。

$\langle \psi | AB | \varphi \rangle = \langle \psi | B^\dagger A^\dagger | \varphi \rangle$（先将 $B\psi$ 视为一体，再作变换）。

### 基矢与本征方程

③角动量的对易式  
= [y, zPx] + [z, xP] = y[P₂, ly] + x[-l, P] = -y(itx) - x(-Py) = ilz

$A | \psi \rangle = \lambda | \psi \rangle$，称 $|\psi\rangle$ 为算符 $A$ 的本征态，$\lambda$ 为本征值。

**能量本征方程**：$H | \psi_k \rangle = E_k | \psi_k \rangle$，将 $|\psi_k\rangle$ 简记为 $|k\rangle$（为基矢），量子数 $k$ 标记系统所有量子数。

## ③ 角动量的对易式

**基本对易关系（右手螺旋关系）**

$[l_x, x] = [yP_z - zP_y, x] = 0$，$[l_\alpha, \alpha] = 0 \quad (\alpha = x, y, z)$

$[l_x, y] = [yP_z, y] - [zP_y, y] = -[zP_y, y] = i\hbar z$（↑y → x，右手螺旋关系）

$[l_x, z] = [yP_z - zP_y, z] = [yP_z, z] = -iy\hbar$

同理有：
$[l_y, x] = -i\hbar z$，$[l_y, z] = i\hbar x$，$[l_z, x] = i\hbar y$，$[l_z, y] = -i\hbar x$

**角动量与动量分量的对易式**

$[l_x, P_x] = [yP_z - zP_y, P_x] = 0$，$[l_\alpha, P_\alpha] = 0 \quad (\alpha = x, y, z)$

$[l_x, P_y] = [yP_z - zP_y, P_y] = [yP_z, P_y] = iP_z$

$[l_x, P_z] = [yP_z - zP_y, P_z] = -[zP_y, P_z] = -iP_y$

同理有：
$[l_y, P_x] = -iP_z$，$[l_y, P_z] = iP_x$，$[l_z, P_x] = P_y$，$[l_z, P_y] = -iP_x$

**角动量分量之间的对易式**

$[l_x, l_x] = 0$，$[l_\alpha, l_\alpha] = 0 \quad (\alpha = x, y, z)$

$[l_x, l_y] = [yP_z - zP_y, zP_x - xP_z] = [yP_z, zP_x] - [yP_z, xP_z] - [zP_y, zP_x] + [zP_y, xP_z]$

$= [y, zP_x] + [z, xP_z] = y[P_z, l_y] + x[-l_z, P_y] = -y(i\hbar x) - x(-i\hbar P_y) = i\hbar l_z$

同理：$[l_y, l_z] = i\hbar l_x$，$[l_z, l_x] = i\hbar l_y$

**角动量平方算符**

令 $l^2 = l_x^2 + l_y^2 + l_z^2 = y^2P_z^2 + z^2P_y^2 - yP_z(zP_y) - zP_y(yP_z)$

则 $l^2 = (x^2 + y^2)P_z^2 + (z^2 + x^2)P_y^2 + (y^2 + z^2)P_x^2 - (yzP_zP_y - yzP_yP_z) - (zxP_zP_x - zxP_xP_z) - (xyP_xP_y - xyP_yP_x)$

**对易式运算恒等式**

$[A, BC] = ABC - BCA = A(BC - CB) + ACB - BCA = A[B, C] + [A, C]B$

B 左移变边缘，可提公因式。

$[AB, C] = (AB - BA)C + BAC - BCA = [A, B]C + B[A, C]$

**重要结论：**

$[A, BC] = [A, B]C + B[A, C]$

$[AB, C] = A[B, C] + [A, C]B$

[A, BC] = [A, B]C + B[A, C]

[AB, C] = A[B, C] + [A, C]B

同理，若 $[A, x] = 0$ 且 $[B, x] = 0$，则 $[AB, x] = 0$。

刚德草学术是到印 RMC
HUAZHONG UNIVERSITY OF SCIENCE AND TECHNOLOGY

-（xzxP2-xx）-（xyPP-itxx）-（yxP-yP)

宏观态 △;可继续细分