# 一维束缚态

在一维情况下，A4=E4 简化为：

$$\left[-\frac{\hbar^2}{2\mu}\frac{d^2}{dx^2}+V(x)\right]\psi(x)=E\psi(x)$$

## 定理 1（势函数不连续时）

设 $V(x)=V_1$（$x<a$），$V(x)=V_2$（$x>a$），在 $x=a$ 处不连续，有一个跳跃。当 $V_1-V_2$ 有限时，能量本征函数 $\psi(x)$ 及其导函数 $\psi'(x)=\frac{d\psi}{dx}$ 在 $a$ 点是连续的。

$\psi(x)$ 本身连续是因为概率幅的连续性问题（$\psi(x)$ 是概率波！）$|\psi(x)|^2$ 有限，$E\to 0$ 时右式 $\to 0$。

**思路 2（反证法）**：若 $\psi'(x)$ 不连续，则 $\psi''(x)$ 含冲击项，不符合薛定谔方程。

**思路 3**：连续性方程 $\frac{\partial \rho}{\partial t}+\nabla\cdot j=0$，其中 $\rho=\psi^*\psi=|\psi|^2$，$j=-\frac{i\hbar}{2\mu}(\psi^*\nabla\psi-\psi\nabla\psi^*)$。连续 $\Rightarrow$ $\psi$、$\psi'$ 连续。

## 一维半无限深方势阱

$$V(x)=\begin{cases} \infty, & x<0 \\ 0, & 0<x<a \\ V_0, & x>a \end{cases}$$

$$\frac{\hbar^2}{2\mu}\frac{d^2\psi}{dx^2}+V(x)\psi(x)=E\psi(x)$$

**$x<0$ 区域**：$\because V(x)=\infty$，则物理上不允许粒子在此区域出现，故有 $\psi(x)=0$（$x<0$）。由连续性，$\psi(0)=0$，则 $\psi(x)=A\sin kx$（$0<x<a$）。

**$x>a$ 区域**：有 $\psi''(x)-\frac{2\mu}{\hbar^2}(V_0-E)\psi(x)=0$。令 $\beta=\frac{\sqrt{2\mu(V_0-E)}}{\hbar}$，则 $\psi(x)=Be^{\beta x}+Ce^{-\beta x}$。

$\because \psi(x)\to 0$（$x\to\infty$），若 $\beta$ 为虚数（即 $V_0<E$），$\psi(x)$ 周期振荡不满足束缚态条件，故仅考虑 $\beta$ 为实数且 $>0$。（$x\to\infty$ 时 $e^{\beta x}\to\infty$，$\therefore C=0$），$\psi(x)=Be^{-\beta x}$。

由 $x=a$ 处连续条件：
$$\psi(a)=Be^{-\beta a}=A\sin ka$$
$$\psi'(a)=-\beta Be^{-\beta a}=kA\cos ka$$

于是有：
$$-k\cot ka=\beta=\frac{\sqrt{2\mu(V_0-E)}}{\hbar}$$

且 $\cot ka<0$。$E$ 满足超越方程：
$$E=\frac{\hbar^2 k^2}{2\mu}\left[1-\cos(2ka)\right]$$

且 $\cot(ka)<0$，**能量是量子化的**。

$$\sin^2 ka=\frac{\hbar^2 k^2}{2\mu a\beta}\sin 2ka$$

## 理想气体微观模型与压强

标准状态下的气体分子数密度 $n_0 = \frac{p_0}{kT_0}$，表示每 $\text{m}^3$ 理想气体中的微观粒子数。

分子线度为 $d$，则 $d \ll \bar{l}$（平均自由程），即可不计分子本身的大小。

**理想气体的微观模型**：
1. 可不计分子本身的大小
2. 除碰撞外，气体分子间及气体分子同器壁间的相互作用可忽略
3. 分子在两次碰撞间做匀速直线运动

**压强的微观模型**：
1. 宏观上认为器壁受连续作用力
2. 热平衡时，假设分子和器壁的碰撞是弹性碰撞
3. 分子混沌性假设：平衡态时，气体分子的热运动速度无择优方向

设第 $i$ 个分子与 $A$ 面碰撞，$y$、$z$ 分量不变，$x$ 方向速度分量由 $v_{ix}$ 变为 $-v_{ix}$。

$$P = \frac{2m n \overline{v_x^2}}{2} = nm\overline{v_x^2}$$

又 $\overline{v_x^2} = \frac{1}{3}\overline{v^2}$，$\overline{v^2} = \frac{3kT}{m}$，$\frac{1}{2}m\overline{v^2} = \bar{\varepsilon}_t$ 为分子的平均平动动能。

$$\therefore P = \frac{2}{3}n\bar{\varepsilon}_t = nkT \Rightarrow \bar{\varepsilon}_t = \frac{3}{2}kT$$

## 分子的平均动能与理想气体系统的内能

只考虑分子平动动能，内能

$$U = N\bar{\varepsilon}_t = \frac{3}{2}NkT = \frac{3}{2}\nu RT$$

定体热容

$$C_V = \left(\frac{\partial U}{\partial T}\right)_V = \frac{3}{2}R，\quad C_{V,m} = \frac{3}{2}R$$

近独立粒子系的麦克斯韦一玻尔兹曼分布能量分布律
一、微观粒子基本运动状态的经典描述(能量、坐标、动量)①自由平动粒子在三维空间中运动时，粒子的自由度为3，位置由$x、y，2标定，与之共的动量为P_{x=mx，$P_{}=my.$P_{2}= mz}，x表示x对时间的导数. 无外力作用时E=2mn（²}+P²+P{2}.粒子状态可由x$y.2，Px}Py}，P2}确定 ②线性谐振子质量为m的粒子在弹性力F=-Ax作用下在平衡点附近作简谐运动，振动圆频率$w=$\}E=x{}=$ $\fra{} {  m}$ $\c{^ra{}{2}$ → 2mε $P^{2}$ + T05 =1 以x、P为直角坐标可构成二维M空间，若ε给定，则代表点的轨迹是椭有圆，椭有圆面积=π$\2me{ 即S=2a③转子(双原子分子整体刚性转动) 考虑质量为m的质点A被具有一定长度的轻杆系于原点时所做运动(r一定)E=\mx^²+y²+z²2).x=rsinθosy=rsinθsin4z=rosθE=m（r²+r²θ²+r²smn²²）=m（r²θ²+r²s²θφ） 对于双原子分子，两质点绕系统质心转动可约化为质量m的单体转动问题.
$1r}$re I总=m，r²2+m2{2=m2 系统转动能量T=m₁r²}^²2+sin²}φ²}）+/m₂2²²2（θ^²+sm2}φ2 即T=mc²θ²+sin²θ²）=（²+sin²θ²）=+++P{=mμre^²θ=Pa₁+Pθ₂2，Pp=mr^²smn²Oφ（与θ、4共轭的动量)T总=mre²θ²+mμFe²sm²θφ²=（P²+sm²θP

## 宏观分布、组态、微观态

### μ空间分割（宏观）

把相空间分成许多小体元 $\Delta\mu_j$（$j=1,2,\cdots,l$），大小适当，足够小到可近似认为代表点落在内的粒子运动状态相同，但也不是无穷小，要满足 $\Delta\omega_j \ge 10$（统计需要）。

### 宏观分布与宏观态

与 $\mu$ 空间的分布 $\{a_j\}$ 对应。宏观状态参量是相应微观物理量的统计平均值。

知道了 $\Delta\mu_j$（$j=1,2,\cdots,l$）体元内代表点的数目 $a_j$（$j=1,2,\cdots,l$），即可确定系统的内能等宏观量的平均值，从而系统的宏观态也就确定了。

### 宏观分布的组态（配容）

（哪些粒子的代表点在 $\Delta\mu_j$ 内）经典力学中，粒子是可分辨的，交换两粒子的状态会改变系统的状态（微观）。一个宏观分布 $\{a_j\}$ 对应的组态数 $W=\{a_j\}$，即将 $N$ 个粒子按 $\{a_j\}$ 分布给 $l$ 个状态的可能数。

### 经典力学中一个组态的微观数

（相字 $\Delta\mu_j$ → 相格 $h^r$，过渡到微观）粒子的状态是连续的，粒子和系统的微观运动状态不可数。人为划出最小的格子，将 $p,q$ 分为等间隔区域，$\delta p_i \delta q_i = h_0$，$(\delta q_1 p_1)\cdots(\delta q_r p_r) = h_0$，相格 $h_0$ 代表一个粒子态。

子相字空间小体元 $\Delta\mu_j$（$j=1,2,\cdots,l$）中粒子运动状态数为 $\Delta\omega_j$，$a_j$ 个粒子在 $\Delta\omega_j$ 个运动状态上分布的可能微观状态数为 $\binom{\Delta\omega_j}{a_j}$。多个粒子可以处于同一相格内。

### 一个分布的微观分布数

$$W = \prod_j \binom{\Delta\omega_j}{a_j} = \prod_j \frac{\Delta\omega_j!}{a_j!(\Delta\omega_j - a_j)!}$$

## 等概率原理和最概然统计

若系统的各微观态无更多限制，就假定一切符合所有约束条件的微观态出现的概率相等。

**最概然统计**：认为出现概率最大（即微观态数最多）的那个宏观态分布对应于系统的平衡态。

## 最概然分布求算

由斯特林公式，当 $M$ 足够大时，有 $\ln M! \approx M\ln M - M$。

则

宏观态 $\Delta_i$ 可继续细分，一种分布有多种实现方法，对应多个组态。
$$\delta(\ln a_j! - \ln \mu!) = \sum (\ln a_j - \ln \mu)\delta a_j = \sum (\ln a_j + \ln a - \ln \mu)\delta a_j = \sum (\ln a_j - \ln \mu)\delta a_j = 0$$

又有粒子数和能量守恒条件（孤立），则
$$\sum \delta a_j = 0, \quad \sum E_j \delta a_j = 0$$

令
$$f(a_1, a_2, \cdots, a_j, \alpha, \beta) = \sum (\ln a_j - \ln \mu) a_j + \alpha\left(\sum a_j - N\right) + \beta\left(\sum E_j a_j - E\right)$$

则 $f$ 取极值时，
$$\frac{\partial f}{\partial a_j} = 0, \quad \frac{\partial f}{\partial \alpha} = 0, \quad \frac{\partial f}{\partial \beta} = 0$$

即
$$\ln a_j + \alpha + \beta E_j = 0$$

$$a_j = \mu_j e^{-\alpha - \beta E_j}$$

且此时 $f$ 取极大值。

$$\beta = \frac{1}{kT}$$，是一个普遍量。

$$a_j = \mu_j e^{-\alpha - \beta E_j}$$

$$\sum a_j = N, \quad \sum E_j a_j = E$$

---

### 宏观态、组态与微观态的关系

- **宏观态**：可继续细分
- **一种分布**：有多种实现方法 → 对应多个**组态**
- **μ空间的分布**：一个组态有多种**微观态**

$$\{a_j\}$$

## 最概然分布求算（续）

### △M 的分割举例

一维线性谐振子 $E=\frac{p^2}{2m}+\frac{1}{2}m\omega^2x^2$，$E=\text{常数}$，代表点的轨迹为椭圆（μ空间）。

$S=\pi\sqrt{\frac{2mE}{m\omega^2}}$，$\Delta E=h\nu$ 时，$\Delta S=h$。

偏离最概然分布的概率很小，平衡态对应的微观态数为 $W$，最概然分布附近一个分布对应的微观态数为 $W'$。假设 $N=2n$ 个粒子处在一个体积 $V$ 的空间中，将 $V$ 等体积划分为 $\Delta M_1, \Delta M_2, \dots$

$$W' = \frac{(2n)!}{(n+\Delta n)!(n-\Delta n)!} = \frac{(2n)!}{n!n!}\cdot\frac{n!n!}{(n+\Delta n)!(n-\Delta n)!}$$

$n$ 很大时，$\frac{\Delta n}{n} \to 0$。

### 量子态中的 μ 空间

$\Delta x \Delta p_x \geq h$，一个粒子的代表点不再是点，而是一团“小空间”。粒子的状态是分立的，不再需要用“μ空间”，只需考虑分立能级上的分布即可。

- **刚性转子能级**：$E = \frac{l(l+1)\hbar^2}{2I}$，$A = \frac{\hbar^2}{2I}$，$\varepsilon_l = l(l+1)A$
- **谐振子能级**：$E = \left(n+\frac{1}{2}\right)h\nu$
- **平动子能级**：间隔极小，可视为连续分布，按 $d\varepsilon$ 分能级；常温下，转动也可看作连续（不含 $H_2$）
- **振动**：一般必须看作分立能级，直接分析量子能级简并度

### 量子态与相空间体积之间的对应关系

对于一个自由度为 $r$ 的粒子，它的 μ 空间中大小为 $h^r$ 的相体积对应一个量子态。

第一象限内，$0 \sim \varepsilon$ 范围内的总量子态数：

$$\Phi(\varepsilon) = \frac{1}{h^3}\cdot\frac{4\pi}{3}\cdot(2m\varepsilon)^{3/2}\cdot V = \frac{4\pi V}{3h^3}(2m\varepsilon)^{3/2}$$

（其中 $V = abc$，$p^2 = p_x^2 + p_y^2 + p_z^2 = 2m\varepsilon$，$\sin\theta$ 积分给出 $4\pi$ 立体角因子）

---

**注意**：以上为跨页内容延续，标题层级与上一页「五、最概然分布求算」保持一致。

算符狄拉克符号 14>：右矢；<41：左矢，称14>或<4为态矢，4是一个标签，用于区分不同的量子态 <41=14>+，左矢与右矢是一种共轭转置关系。<ap1=a*<φ1(a为复数) 内积：(4，4)=<414> 坐标表象 -∞φ*（P)4(r)dt，dt=dxdydz为微体积元，p(²)=4(x，y，,z)<41p>=<414>，用定积分理解是共规，用矩阵理解是转置后取共轭. 正交：<41φ>=0代表4和φ是正交的归一：<414>=1代表4是归一化的平均值：力学量A在归-化量子态4下的平均值A=<41A14>14>、<是量子态4在右矢，左矢空间的不同表示
左、右矢空间的算符运算设A和A是两个算符，V14>和14)，若(4|A14>=<PA14>，则称A为A的转置算符 =A4，在右矢空间中，14>=14>=1A4>，默认A向右作用，在左矢空间中，<41=<41A{}，算符A^{+}(A^{)向左作用。<41A^=<A41=<41.若A为厄米算符，则<41=<41A. 厄米算符在左、右矢空间中的运算具有形式不变性算符在左矢和右矢之间的转换本质上是对偶空间的伴随映射。
关于（1A4>）=<41A：A=<41A14>，A=<41A14>，^=<41A4=<A414><A41=<A<AB41=<41B+}^+（先将B4视为一体，再作变换).
基矢与本征方程 14>=λ14)，称(4>为算符f的本征态，入为本征值. 能量本征方程：H14k>=Ek14k)，将14k)简记为|k>(为基矢)，量子数k标记系统所有量子数.

## 角动量的对易式

刚德草学术是到印 RMC

HUAZHONG UNIVERSITY OF SCIENCE AND TECHNOLOGY

### 角动量的对易式

$$=x_2=x_2=1\ e_x\ x_3\ 2\ 2_2^1+2+xx_1=z-²dh=(z-h)-=×1\ 2dx-yz=（x-xz)4！-=1\ l_z=-it（x-y=x-y[l_x，x]=[yP-z，x]=0\ [l_a，α]=0\ (a=x，y，z)$$

$$[l_x，y]=[yP，y]-[zP，y]=-[zP，y]=ihz\ \uparrow y \rightarrow x\ \$ 右手螺旋关系$$

$$[l_x，z]=[yP-zP_y，2]=[yB_2，z]=-iy\ \$(e^{xe{2}=-ey)$$

同理有 $[l_y，x]=-ihz$，$[l，z]=ix$，$[l_2，x]=ity$，$[l，y]=-ix$.

$$[x，]=[yP-2，P]=0\ \ l_a，P]=0\ \ α=x，y，z$$

$$[l_x，P]=[yP-2，]=[yP，P]=[，-i]=iP\ \ \$2_xxey}=^_\$$$

$$[l_x，P²]=[yP_2-2P_y，P₂I=-[2P，P_2]=-itP\ \ \$e{xe{2}=--\$$$

同理有 $[l_y，B]=-i$，$[l，]=$，$[，P]P，₂，P_y]=-iP$.

$$[l_x，l_x]=0\ \ [l_a，l_a]=0\ \ (a=x，y，z)$$

$$[l，l]=[yP-2，zP-x]=[y，z]-]-[+[z，xP]=[y，zP_x]+[z，xP]=y[P₂，l_y]+x[-l，P=-y（itx）-x（-P_y）=il_z$$

同理，$[l_y，]=itx$，$[l，]=l_y$.

令 $²=²+y²+²=y²P²+z²²-yP_2（zP）-2P（yP$，则

$$=（x²+y²）²+z+x）²+（y²+2²²-（yz4P_2-）-（yzPP-₂-（zxP-zP）-（xzxP_2-xx）-（xyPP-itxx）-（yxP-yP)$$

$$[A，BC]=ABC-BCA=A(BC-CB）+ACB-BCA=ABC]+CACB+CAB-BCA=A[B，C]A，CB$$

**B左移变边缘，可提公因式**

$$H[CA，B]=(AB-BA）C+BAC-BCA=[A，B]C+B[A，C]$$

$$[A，BC]=[A，B]C+B[A，C]$$