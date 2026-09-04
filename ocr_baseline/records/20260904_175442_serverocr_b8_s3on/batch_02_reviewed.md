④常见对易恒等式

A、B为厄米算符，则 $\langle \psi | (\hat{A} - i\hat{B})^\dagger (\hat{A} + i\hat{B}) | \psi \rangle \geq 0$，展开得 $\langle \psi | \hat{A}^2 | \psi \rangle + \langle \psi | \hat{B}^2 | \psi \rangle + i\langle \psi | [\hat{A}, \hat{B}] | \psi \rangle \geq 0$，即 $\Delta A^2 + \Delta B^2 \geq i\langle [\hat{A}, \hat{B}] \rangle$，由此可导出 $\Delta A \Delta B \geq \frac{1}{2} |\langle [\hat{A}, \hat{B}] \rangle|$。

$[A,B]=-[B,A]$

$[A,B+C]=[A,B]+[A,C]$

$[A,BC]=[A,B]C+B[A,C]$

$[AB,C]=A[B,C]+[A,C]B$

$[A,B+C]+[B,A+C]+[C,A+B]=0$

$[A,[B,C]]+[B,[C,A]]+[C,[A,B]]=0$（对称）

**利用对易关系求解平均值问题**

**例1.** 求 $\hat{L}_x$ 和 $\hat{L}_y$ 在 $|l m\rangle$ 下的平均值。

$\hat{L}_z |l m\rangle = m\hbar |l m\rangle$，$[\hat{L}_y, \hat{L}_z] = i\hbar \hat{L}_x$，$[\hat{L}_z, \hat{L}_x] = i\hbar \hat{L}_y$，从而可用含 $\hat{L}_z$ 的表达式表出 $\hat{L}_x$。

$\langle \hat{L}_x \rangle = \langle l m | \hat{L}_x | l m \rangle = \frac{1}{i\hbar} \langle l m | [\hat{L}_y, \hat{L}_z] | l m \rangle = \frac{1}{i\hbar} [\langle l m | \hat{L}_y \hat{L}_z | l m \rangle - \langle l m | \hat{L}_z \hat{L}_y | l m \rangle]$

$\hat{L}_z |l m\rangle = m\hbar |l m\rangle$，$m$ 为实数，则 $\langle l m | \hat{L}_z = m\hbar \langle l m |$。

$\langle \hat{L}_x \rangle = \frac{1}{i\hbar} [m\hbar \langle l m | \hat{L}_y | l m \rangle - m\hbar \langle l m | \hat{L}_y | l m \rangle] = \frac{m}{i} [\langle l m | \hat{L}_y | l m \rangle - \langle l m | \hat{L}_y | l m \rangle] = 0$

$\langle \hat{L}_x \rangle = \langle \hat{L}_y \rangle = 0$

**例2.** $|l m\rangle$ 为 $(\hat{L}^2, \hat{L}_z)$ 的共同本征态，求 $\langle \hat{L}_x^2 \rangle$，$\langle \hat{L}_y^2 \rangle$。

$\hat{L}^2 |l m\rangle = l(l+1)\hbar^2 |l m\rangle$

$\langle \hat{L}_z^2 \rangle = \langle l m | \hat{L}_z^2 | l m \rangle = m^2 \hbar^2$

$[\hat{L}_y, \hat{L}_z] = i\hbar \hat{L}_x$，$\hat{L}_x = \frac{1}{i\hbar} (\hat{L}_y \hat{L}_z - \hat{L}_z \hat{L}_y)$

$\hat{L}_x^2 = \frac{1}{i\hbar} (\hat{L}_y \hat{L}_z - \hat{L}_z \hat{L}_y) \cdot \frac{1}{i\hbar} (\hat{L}_y \hat{L}_z - \hat{L}_z \hat{L}_y) = -\frac{1}{\hbar^2} (\hat{L}_y \hat{L}_z \hat{L}_y \hat{L}_z - \hat{L}_y \hat{L}_z^2 \hat{L}_y - \hat{L}_z \hat{L}_y^2 \hat{L}_z + \hat{L}_z \hat{L}_y \hat{L}_z \hat{L}_y)$

$\langle \hat{L}_x^2 \rangle = \langle l m | \hat{L}_x^2 | l m \rangle = \frac{1}{\hbar^2} \langle l m | (\hat{L}_y \hat{L}_z^2 \hat{L}_y + \hat{L}_z \hat{L}_y^2 \hat{L}_z - \hat{L}_y \hat{L}_z \hat{L}_y \hat{L}_z - \hat{L}_z \hat{L}_y \hat{L}_z \hat{L}_y) | l m \rangle$

$= \frac{1}{\hbar^2} [m^2 \hbar^2 \langle \hat{L}_y^2 \rangle + m^2 \hbar^2 \langle \hat{L}_y^2 \rangle - m\hbar \langle \hat{L}_y \hat{L}_z \hat{L}_y \rangle - m\hbar \langle \hat{L}_y \hat{L}_z \hat{L}_y \rangle]$

$= \frac{1}{\hbar^2} [2m^2 \hbar^2 \langle \hat{L}_y^2 \rangle - 2m\hbar \cdot m\hbar \langle \hat{L}_y^2 \rangle] = \frac{1}{\hbar^2} [2m^2 \hbar^2 \langle \hat{L}_y^2 \rangle - 2m^2 \hbar^2 \langle \hat{L}_y^2 \rangle] = 0$

$\langle \hat{L}_x^2 \rangle = \langle \hat{L}_y^2 \rangle = \frac{1}{2} [l(l+1) - m^2] \hbar^2$

**方法**：将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

# 不确定度关系的严格证明

任意给定力学量 $A$ 和 $B$，对应的厄米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \Delta B \geq \frac{1}{2} |\langle [\hat{A}, \hat{B}] \rangle|$$

其中 $\langle [\hat{A}, \hat{B}] \rangle = \langle \Psi | [\hat{A}, \hat{B}] | \Psi \rangle$ 对 $\forall |\Psi\rangle$ 成立，$\Delta A = \hat{A} - \langle A \rangle$，$\Delta B = \hat{B} - \langle B \rangle$。

$$[\hat{A}, \hat{B}] = [\Delta A + \langle A \rangle, \Delta B + \langle B \rangle] = (\Delta A + \langle A \rangle)(\Delta B + \langle B \rangle) - (\Delta B + \langle B \rangle)(\Delta A + \langle A \rangle) = [\Delta A, \Delta B]$$

$$\Delta A = \sqrt{\langle \hat{A}^2 \rangle - \langle \hat{A} \rangle^2}, \quad \Delta B = \sqrt{\langle \hat{B}^2 \rangle - \langle \hat{B} \rangle^2}$$

要证，也即 $\langle (\hat{A} - \langle A \rangle)^2 \rangle \cdot \langle (\hat{B} - \langle B \rangle)^2 \rangle \geq \frac{1}{4} |\langle [\hat{A} - \langle A \rangle, \hat{B} - \langle B \rangle] \rangle|^2$。

令 $\hat{A}' = \hat{A} - \langle A \rangle$，$\hat{B}' = \hat{B} - \langle B \rangle$，要证变为：

$$\langle \hat{A}'^2 \rangle \cdot \langle \hat{B}'^2 \rangle \geq \frac{1}{4} |\langle [\hat{A}', \hat{B}'] \rangle|^2$$

联想 $b^2 \geq 4ac$。考虑 $|\Psi\rangle = \xi \hat{A}' |\Psi\rangle + i \hat{B}' |\Psi\rangle$，$\langle \Psi | \Psi \rangle \geq 0$：

$$\langle \xi \hat{A}' |\Psi\rangle + i \hat{B}' |\Psi\rangle, \xi \hat{A}' |\Psi\rangle + i \hat{B}' |\Psi\rangle \rangle = (\xi \langle \Psi | \hat{A}' + (-i) \langle \Psi | \hat{B}')(\xi \hat{A}' |\Psi\rangle + i \hat{B}' |\Psi\rangle)$$

$\hat{A}, \hat{B}$ 为厄米算符：

$$= (\xi \langle \Psi | \hat{A}' - i \langle \Psi | \hat{B}')(\xi \hat{A}' |\Psi\rangle + i \hat{B}' |\Psi\rangle)$$

$$= (\xi \langle \Psi | \hat{A}' + (-i) \langle \Psi | \hat{B}')(\xi \hat{A}' |\Psi\rangle + i \hat{B}' |\Psi\rangle)$$

$$= \xi^2 \langle \Psi | \hat{A}'^2 |\Psi\rangle + \langle \Psi | \hat{B}'^2 |\Psi\rangle + i\xi (\langle \Psi | \hat{A}' \hat{B}' |\Psi\rangle - \langle \Psi | \hat{B}' \hat{A}' |\Psi\rangle) = \xi^2 \langle \hat{A}'^2 \rangle + \langle \hat{B}'^2 \rangle + i\xi \langle [\hat{A}', \hat{B}'] \rangle \geq 0$$

由 $\langle \Psi | \Psi \rangle \geq 0$，判别式 $\leq 0$，即 $\langle [\hat{A}', \hat{B}'] \rangle^2 \leq 4 \langle \hat{A}'^2 \rangle \cdot \langle \hat{B}'^2 \rangle$，即 $\langle \hat{A}'^2 \rangle \cdot \langle \hat{B}'^2 \rangle \geq \frac{1}{4} |\langle [\hat{A}', \hat{B}'] \rangle|^2$。

因此：

$$\Delta A \Delta B \geq \frac{1}{2} |\langle [\hat{A}, \hat{B}] \rangle|$$

**对任意力学量 $A, B$ 及量子态 $|\Psi\rangle$，若 $A$ 与 $B$ 不对易，即 $[\hat{A}, \hat{B}] \neq 0$，则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 $A$ 与 $B$ 不能同时被精确测定。**

## 共同本征函数

设 $\hat{A} \psi_A = A \psi_A$，$\hat{B} \psi_B = B \psi_B$。若 $[\hat{A}, \hat{B}] \neq 0$，则 $\psi_A$ 不是 $\hat{B}$ 的本征函数，$\psi_B$ 不是 $\hat{A}$ 的本征函数。

若 $[\hat{A}, \hat{B}] = 0$，则可能存在 $\psi$，使 $\hat{A}\psi = A\psi$，$\hat{B}\psi = B\psi$。此时称 $\psi$ 为 $A$ 和 $B$ 的共同本征函数。

**定理**：设 $\hat{A}|k\rangle = a_k |k\rangle$，另有 $\hat{B}$，若 $[\hat{A}, \hat{B}] = 0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $A$ 和 $B$ 拥有共同本征态。

证明：$[\hat{A}, \hat{B}] = 0 \Rightarrow \hat{A}\hat{B} = \hat{B}\hat{A}$。$\hat{B}\hat{A}|k\rangle = \hat{B} \cdot a_k |k\rangle = a_k \hat{B}|k\rangle$。则 $\hat{A}(\hat{B}|k\rangle) = a_k (\hat{B}|k\rangle)$，故 $\hat{B}|k\rangle$ 也是 $\hat{A}$ 属于本征值 $a_k$ 的本征态。由于 $a_k$ 不简并，$\hat{B}|k\rangle$ 与 $|k\rangle$ 是同一个量子态，即 $\hat{B}|k\rangle = b_k |k\rangle$。$\Rightarrow A, B$ 拥有共同本征态 $|k\rangle$。

**例**：$\hat{p}_x \psi_{\vec{p}}(\vec{r}) = p_x \psi_{\vec{p}}(\vec{r})$，$\hat{p}_x, \hat{p}_y, \hat{p}_z$ 的共同本征函数，本征值为 $p_x, p_y, p_z$。

$$\hat{p} \psi_{\vec{p}}(\vec{r}) = \left( \frac{\hbar}{i} \nabla \right) \psi_{\vec{p}}(\vec{r}) = \vec{p} \, \psi_{\vec{p}}(\vec{r})$$

$$\psi_{\vec{p}}(\vec{r}) = \frac{1}{(2\pi\hbar)^{3/2}} e^{i\vec{p} \cdot \vec{r}/\hbar}$$

## 厄米算符本征值与本征态的特性

### 转置算符、共轭算符与厄米算符

转置算符：对 $\hat{A}$ 和 $\hat{B}$，若 $\langle \psi|\hat{A}|\phi\rangle = \langle \phi|\hat{B}|\psi\rangle$，则称 $\hat{A}$ 和 $\hat{B}$ 互为彼此的转置算符。

共轭算符：对算符 $\hat{A}$ 的每一项取复共轭，得到 $\hat{A}^*$ 为 $\hat{A}$ 的转置算符。

**厄米算符**：$\hat{A} = \hat{A}^\dagger = \hat{A}^*$，则称 $\hat{A}$ 为厄米算符。

**定理**：厄米算符 $\hat{A}$ 在任意量子态下的平均值 $\bar{A}$ 为实数，$\hat{A}^2$ 的平均值 $\overline{A^2} \geq 0$。

$$\langle \psi|\hat{A}|\psi\rangle = \langle \psi|\hat{A}^\dagger|\psi\rangle = \langle \psi|\hat{A}^*|\psi\rangle = \langle \psi^*|\hat{A}|\psi^*\rangle = (\langle \psi|\hat{A}|\psi\rangle)^*$$

由 $\hat{A} = \hat{A}^*$，$\bar{A}$ 为实数。

或：

$$\langle \psi|\hat{A}^\dagger|\psi\rangle = \langle \hat{A}\psi|\psi\rangle, \quad \langle \psi|\hat{A}|\psi\rangle = \langle \hat{A}\psi|\psi\rangle, \quad \hat{A} = \hat{A}^\dagger = \hat{A}^*, \quad \bar{A} \text{ 为实数}$$

$$\langle \psi|\hat{A}^2|\psi\rangle = \langle \psi|\hat{A}\hat{A}|\psi\rangle = \langle \psi|\hat{A}^\dagger\hat{A}|\psi\rangle = \langle \hat{A}\psi|\hat{A}\psi\rangle = \langle \phi|\phi\rangle \geq 0, \quad \overline{A^2} \geq 0$$

其中 $|\phi\rangle = \hat{A}|\psi\rangle$。

### 厄米算符本征值的实数性

设 $\hat{F}|k\rangle = \lambda_k |k\rangle$，则

$$\langle k|\hat{F}|k\rangle = \bar{F} = \langle k|\lambda_k |k\rangle = \lambda_k \langle k|k\rangle = \lambda_k$$

由 $\lambda_k = \bar{F}$ 为实数，**厄米算符的本征值必为实数**。

### 厄米算符本征态的正交性与完备性、封闭性

**① 正交性**：厄米算符属于不同本征值的本征态必然正交。

（对不同 $|k\rangle$ 可能有不同的 $\lambda_k$）

$$\hat{F}|k\rangle = \lambda_k |k\rangle, \quad \hat{F}|k'\rangle = \lambda_{k'} |k'\rangle$$

$$\langle k'|\hat{F}|k\rangle = \lambda_k \langle k'|k\rangle, \quad \langle k'|\hat{F}|k\rangle = \langle k'|\hat{F}^\dagger|k\rangle = \langle \hat{F}k'|k\rangle = \lambda_{k'} \langle k'|k\rangle$$

又 $\lambda_k$ 为实数，$\lambda_k = \lambda_k^*$，故

$$\langle k'|\hat{F}|k\rangle = \lambda_k \langle k'|k\rangle = \lambda_{k'} \langle k'|k\rangle$$

而 $\lambda_k \neq \lambda_{k'}$，所以 $\langle k'|k\rangle = 0$，即 $|k'\rangle$ 与 $|k\rangle$ 正交。

**② 本征态的完备性**：$\hat{P} = |k\rangle\langle k|$ 为投影算符，$\hat{P} = \sum_k \hat{P}_k$。

若对 $\forall |\psi\rangle$，有 $\hat{P}|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = |\psi\rangle$，则称基矢 $|k\rangle$ 具有完备性。（任意 $|\psi\rangle$ 可按 $|k\rangle$ 展开）

记 $c_k = \langle k|\psi\rangle$，则 $|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = \sum_k c_k |k\rangle$，$c_k$ 为用 $|k\rangle$ 将 $|\psi\rangle$ 做展开时的展开系数。

**定理**：哈密顿算符 $\hat{H}$ 为厄米算符，满足本征方程 $\hat{H}|k\rangle = E_k |k\rangle$。对体系的任一归一化态 $|\psi\rangle$，若 $\bar{H} = \langle \psi|\hat{H}|\psi\rangle$ 有下界（总大于某常数）但无上界，则 $\hat{H}$ 的本征态 $|k\rangle$ 的集合构成体系的一个完备集，即体系的任一量子态 $|\psi\rangle$ 可用 $|k\rangle$ 来展开。

0,x<0
>An=√/z[a-Seka+tsin2(kna)]*
√n(X)=<Ansin(knx),O<x<a
Bn=z[a-zknsin(2kna)+tnsin(kna)]+.eaposinkna
# 一个En对应一个／n
## 一维谐振子 V(x)=2±2Kx2=/±Mw2x2
(-Kx=mx,x+ax=0,w2=m) 薛定谔方程：[﹣聶器＋/mw2x2]4(0)=E4(x) 令α=x,§=αx，入＝磊．记4(x)=(4(§(x0)=(5)．于是，-x2(4(3)=-(4(). 帶﹣端5(4(3)＝一π(4(3),)-52(4(s)＝一入4(3),2+（入﹣5)4(3)=0 为"消除"32项，试探设4(3)=e-2H(3)=>A)-23+（入﹣1)H(S)=0.4(8)0．仅当入＝2n+1时，Hn(3）有4(3)∞O解，H(S)=Ha(3)=(-1)"e3器e".(?)H(s)H.(3)es ds=n2".n! 8nn(?)4n(s)=Nne-2Ha(3),NaeHa(S)H,(s)dx=(x)4,(x)dx=1,Nn=／反·[/T·2°-n!]+()·/zm 能量分立化 En＝孕hw=(n+z)tcw4n(x)=N.e-Ha(ax) 补充（方程）-23+（入﹣1)H(S)=O的两种解法）①幂级数解法，构造递推的系数关系 H(S)＝盖Q;8,zli(i-n)a;si2-2jajsi+（入﹣)a;S']=O=>(j+2)(j+1)aj+2-(2j+1﹣入）aj=0i、aj+2=aj，若级数解存在无穷多项，aj喻，H(s)~2(5)*=ce>(4(3）按e量级增长，不可积＝＞级数存在（只有）有限项＝→3an≠0,an+2=0，即入＝2n+1. 从而有aj22＝品aj，多项式H(S）只能含奇数项或偶数项，系数由高次项推至低次项方程可变化为）-25+2nH(s)=O，其解为厄米多项式Hn(3).HuS)=(2s)k=(-1)"e(e-s)（可通过递推＋母函数求解）
Hn(s）满足：Hnti(3)-2SHn(s)+2NHm(3)=O 母函数W(t,x)=ex+x-++2(t-x)4(t,x)=01701572
华中科技大学附属印刷厂 W(t,x)=【Ha(x)．箭第

### 守恒量与能级简并度

在量子力学中，若某力学量 $A$ 与哈密顿算符 $\hat{H}$ 对易，即 $[A, \hat{H}] = 0$，则 $A$ 为守恒量。守恒量的本征值不随时间变化，且其本征态可同时为 $\hat{H}$ 的本征态。若体系存在简并，即同一能级 $E_n$ 对应多个线性无关的本征态，则这些本征态张成简并子空间。守恒量 $A$ 在该子空间内的矩阵表示可被对角化，从而提供区分简并态的量子数。能级简并度 $g_n$ 等于该子空间的维数，且守恒量的存在往往导致简并度的增加或对称性相关的简并结构。

# 一维谐振子（续）

## 本征态的封闭性

$\hat{I}$ 为单位算符，$\forall |\psi\rangle$，$\hat{I}|\psi\rangle = |\psi\rangle$。若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = \hat{I}$，称为本征态或基矢 $|k\rangle$ 的**封闭性**；$\sum_k \hat{P}_k = \sum_k |k\rangle\langle k| = \hat{I}$，称为投影算符 $\hat{P}_k$ 的封闭性。

**完备性与封闭性**：强调重点不同。完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开；封闭性指数学上封闭性方程 $\sum_k |k\rangle\langle k| = \hat{I}$ 成立。两者相互依存。

**例**：设体系的能量本征方程为 $\hat{H}|k\rangle = E_k|k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k |k\rangle\langle k|$（本征态具有完备性、封闭性）。

$\hat{H}|k\rangle\langle k| = E_k|k\rangle\langle k|$，则 $\sum_k \hat{H}|k\rangle\langle k| = \hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k|k\rangle\langle k|$，从而有 $\hat{H}\hat{I} = \hat{H} = \sum_k E_k|k\rangle\langle k|$。

## 守恒量与能级简并度

### 力学量平均值的时间依赖特性

$\bar{A}(t) = \langle \psi(t)|\hat{A}|\psi(t)\rangle$。

薛定谔方程：$i\hbar\frac{\partial}{\partial t}|\psi(t)\rangle = \hat{H}|\psi\rangle$。在左矢空间中：$-i\hbar\frac{\partial}{\partial t}\langle\psi| = \langle\psi|\hat{H}$（$\hat{H}^\dagger = \hat{H}$）。

$$\frac{d\bar{A}}{dt} = \frac{d}{dt}\left(\langle\psi|\hat{A}|\psi\rangle\right) = \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle + \frac{i}{\hbar}\langle\psi|[\hat{H},\hat{A}]|\psi\rangle$$

即 $\frac{d\bar{A}}{dt} = \frac{i}{\hbar}\langle\psi|[\hat{H},\hat{A}]|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle$。

若 $\frac{\partial \hat{A}}{\partial t} = 0$（$\hat{A}$ 不显含 $t$）且 $[\hat{H},\hat{A}] = 0$，则 $\frac{d\bar{A}}{dt} = 0$，$\bar{A}$ 与时间无关——$\hat{A}$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随时间改变。

### 守恒量

$\hat{A}$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $\hat{A}$ 对应的力学量为体系的一个**守恒量**。

$\frac{\partial \hat{A}}{\partial t} = 0$ 且 $[\hat{H},\hat{A}] = 0 \Rightarrow \hat{A}$ 为守恒量。

**定理**：若 $[\hat{F},\hat{H}] = 0$，$[\hat{G},\hat{H}] = 0$，但 $[\hat{F},\hat{G}] \neq 0$，则体系的能级是简并的。（$\hat{F}$、$\hat{G}$ 为守恒量）

$\hat{F}$、$\hat{H}$ 有共同本征函数 $\psi$：$\hat{F}\psi = F\psi$，$\hat{H}\psi = E\psi$。

$[\hat{G},\hat{H}] = 0$，则 $\hat{G}\hat{H}\psi = \hat{H}\hat{G}\psi \Rightarrow \hat{H}(\hat{G}\psi) = E(\hat{G}\psi)$。

又 $\hat{G}\hat{F}\psi = \hat{F}\hat{G}\psi \neq F\hat{G}\psi$（因 $[\hat{F},\hat{G}] \neq 0$），则 $\hat{G}\psi$ 不是 $\hat{F}$ 的本征态，$\hat{G}\psi$ 和 $\psi$ 不是一个态，即 $E$ 对应至少两个态，**能级简并**。

# 表象变换与矩阵力学

设 $F=(A_1,A_2,\dots,A_n)$ 是一组力学量完全集，$|k\rangle$ 是它们的共同本征态，其中 $k$ 表征所有量子数。$|k\rangle$ 是正交归一的，满足 $\langle k|m\rangle=\delta_{km}=\begin{cases}1,&k=m\\0,&k\neq m\end{cases}$，$|k\rangle$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。

$\{|k\rangle\}$ 构成一个表象，可称为 $F$ 表象。$F$ 构成无穷维的希尔伯特空间，量子态 $|\psi\rangle$ 是希尔伯特空间中的一个矢量。$|\psi\rangle=\sum_k a_k|k\rangle$，则 $a_k=\langle k|\psi\rangle$ 为内积，也可视为"投影"。

## 表象间的转化

在 $F$ 表象中，$|k\rangle$ 为基矢，$|\psi\rangle=\sum_k a_k|k\rangle$，$|\psi\rangle$ 在 $F$ 表象中可用系数列向量表示为 $a$。另一 $F'$ 表象中，$|\beta\rangle$ 为基矢，$|\psi\rangle=\sum_\beta a_\beta|\beta\rangle$，在 $F'$ 表象中可表示为 $a'=(a_\beta)$。$a'$ 与 $a$ 的转化实际上是基矢之间的转化。

$|\psi\rangle=\sum_k a_k|k\rangle=\sum_\beta b_\beta|\beta\rangle$，$|k\rangle=\sum_\beta \langle\beta|k\rangle\cdot|\beta\rangle$（$|k\rangle$ 按 $|\beta\rangle$ 展开），从而统一基矢为 $|\beta\rangle$。记 $S_{\beta k}=\langle\beta|k\rangle$，$S=(S_{\beta k})$。

则 $a_\beta=\sum_k a_k\cdot\langle\beta|k\rangle$，$a'=Sa$。

**注**：$a$、$a'$ 均为系数列向量，与本征态形式相似但意义完全不同。$|k\rangle$ 在希尔伯特空间中可表示为一个列向量，$|\psi\rangle$ 按 $|k\rangle$ 展开所得系数列为 $a$。

从矢量的角度考虑，$|\psi\rangle=(e_1,e_2,\dots,e_n,\dots)$ 列向量 $e_i'$ 的线性组合系数列。要"消去" $(e_1',e_2',\dots,e_n',\dots)$，则 $(e_1,e_2,\dots,e_n,\dots)=(e_1',e_2',\dots,e_n',\dots)S$，其中

$$S=\begin{pmatrix}S_{11}&S_{12}&\dots&S_{1k}&\dots\\S_{21}&S_{22}&\dots&S_{2k}&\dots\\\vdots&\vdots&&\vdots&\\S_{k1}&S_{k2}&\dots&S_{kk}&\dots\\\vdots&\vdots&&\vdots&\end{pmatrix}$$

由 $\langle k'|k\rangle=\delta_{k'k}$，$\langle k|k\rangle=1$，$|k\rangle=\sum_\beta S_{\beta k}|\beta\rangle$，$\langle k'|k\rangle=\left(\sum_\beta S_{\beta k'}^*\langle\beta|\right)\left(\sum_\beta S_{\beta k}|\beta\rangle\right)=\sum_\beta |S_{\beta k}|^2=1$。

$\langle m|k\rangle=\left(\sum_\beta S_{\beta m}^*\langle\beta|\right)\left(\sum_\beta S_{\beta k}|\beta\rangle\right)=\delta_{mk}$。

**S 为么正矩阵**。

$(e_1,e_2,\dots,e_n,\dots)=(e_1',e_2',\dots,e_n',\dots)\begin{pmatrix}(e_1,e_1')&(e_1,e_2')&\dots\\(e_2,e_1')&(e_2,e_2')&\dots\\\vdots&\vdots&\end{pmatrix}=(e_1',e_2',\dots)S$

中心力场疟＝-DV(2),V(7)=V(r)，称为中心力场 √2在坐标表象下为＋+，采用球坐标表示为▽2=(P剂）+F2sng晶（smo品）+rishre和又个＝一片［s弱（smo录）+s瓶制，于是A4＝一范产乔（r剂4+[3+v(r)]4=E4 采用分离变量法，令4(r,0,4)=R(r)Y(0,4)，则一最广奇（r警）Y(0,4)+(V(N)-E)R(r)Y(0,p)-(sho (sinoY).Rir)+smR(r)]=0 一（)+(V(r-E)=·[(sing)+]1明（2)+2F[E-V(N]=-[so(sin)+]＝入． 经向方程：[rr&P]+［等（E-v(r)-]R(r)=O 角向方程：5(sine)+＝一入Y(,4)，即℃2Y(0,4)＝入た2Y10,4)
①考虑角向方程．Y(8,4)=④(0）中（4)se o[sined中（4)+s④(o)＝一入（0)(4)=＞晶［sine]+＋入sin=0>[sime]＋入sin2e=-)=m2sinea[singd]+(a-3)④(8)=0…勒让德方程 (2+m2（中（4)=0=→中m(p)==eimv 对于勒让德方程smedh[sine]+（入﹣s)④(0)=0，为使④(0）在区间［0,π］有限，入只能取 (((+1),(=0,1,2,…(l为轨道量子数）H(0)=④Lm(8)=P.lm(casB)=Bim(1-cos2o)aPi(cosO)
|m]≤l时才有④(⊙)≠O=)m=0,±1,..,±l.。(o)④(o)sino do=Sei,Bim=
-m(2+,Yim(0,P)=⑨cm(8)Pm(4)=Num(1-cos20)2(a(ooPr(coso)]eimb
Nim=2，球谐函数满足正交关系：。。Yu(0.4)Ycm(0,4)sinodod4=Sr'lSm'm4π(Hm).(2Yum=l(l+1）片2Yum,122Yum=r2m2Yum=>Yum是C2.2的共同本征态

# 氢原子径向方程与能级

**华中科技大学**

## 氢原子径向方程

氢原子径向方程：

$$\left[\frac{d^2}{dr^2} + \frac{2\mu}{\hbar^2}\left(E - V(r) - \frac{l(l+1)\hbar^2}{2\mu r^2}\right)\right]R(r) = 0$$

其中 $V(r) = -\frac{e^2}{4\pi\varepsilon_0 r}$，令 $k = \frac{\mu e^2}{4\pi\varepsilon_0 \hbar^2}$，则方程为：

$$\left[\frac{d^2}{dr^2} + \frac{2\mu}{\hbar^2}\left(E + \frac{k}{r}\right) - \frac{l(l+1)}{r^2}\right]R(r) = 0$$

引入约化径向波函数 $u(r) = rR(r)$，则 $u(r)$ 满足：

$$\left[\frac{d^2}{dr^2} + \frac{2\mu}{\hbar^2}\left(E + \frac{k}{r}\right) - \frac{l(l+1)}{r^2}\right]u(r) = 0$$

当 $r \to \infty$ 时，薛定谔方程约为 $\frac{d^2u}{dr^2} + \frac{2\mu E}{\hbar^2}u(r) = 0$。若 $E > 0$，$u(r)$ 呈振荡形式，不满足束缚态条件，则 $E < 0$。从能量角度分析，$E = V + K$，$K < |V|$，故 $E < 0$。

### 核与电子"双星模型"

$M$ 为约化质量，$M = \frac{m_e m_N}{m_e + m_N}$。定义无量纲变量 $\rho = \alpha r$，$\alpha = \frac{\sqrt{-2ME}}{\hbar}$，$\beta = \frac{Mk}{\hbar^2 \alpha}$，于是方程化为：

$$\left[\frac{d^2}{d\rho^2} + \frac{\beta}{\rho} - \frac{l(l+1)}{\rho^2} - \frac{1}{4}\right]u(\rho) = 0$$

$\rho \to \infty$ 时，方程近似为 $\frac{d^2u}{d\rho^2} - \frac{1}{4}u(\rho) = 0$，$u(\rho) \sim e^{-\rho/2}$（$\rho \to \infty$）。

$\rho \to 0$ 时，方程近似为 $\frac{d^2u}{d\rho^2} - \frac{l(l+1)}{\rho^2}u(\rho) = 0$，$u(\rho) \sim \rho^{l+1}$。

利用渐进解，设 $u(\rho) = \rho^{l+1} e^{-\rho/2} v(\rho)$。$v(\rho)$ 满足方程：

$$\rho \frac{d^2v}{d\rho^2} + (2l + 2 - \rho)\frac{dv}{d\rho} + [\beta - (l+1)]v(\rho) = 0$$

此为合流超几何方程。$v(\rho)$ 有多项式解的条件是 $\beta - (l+1) = n_r$，即 $\beta = l + 1 + n_r$（$n_r = 0, 1, 2, \ldots$）。令 $n = l + 1 + n_r$，$n = 1, 2, \ldots$

$$E_n = -\frac{Mk^2}{2\hbar^2 n^2}$$

$$\beta = \frac{Mk}{\hbar^2 \alpha} = n, \quad E_n = -\frac{Mk^2}{2\hbar^2 n^2} \text{ 仅与 } n \text{ 相关}$$

### 量子数与角动量

$l$ 的取值为 $0, 1, \ldots, n-1$；$m$ 的取值为 $-l, -(l-1), \ldots, 0, 1, \ldots, l$。能量本征态由 $(n, l, m)$ 表征。

氢原子轨道角动量的取值：

$$L^2 = \lambda \hbar^2 = l(l+1)\hbar^2, \quad \hat{L}^2 Y = \lambda \hbar^2 Y$$

氢原子轨道角动量 $z$ 方向的取值：

$$L_z = m\hbar, \quad \hat{L}_z Y = m\hbar Y$$

### 归一化与能级简并

归一化条件：

$$\int_0^\infty |u_{nl}(r)|^2 dr = \int_0^\infty |R_{nl}(r)|^2 r^2 dr = 1$$

$$\int_0^{2\pi} \int_0^\pi \int_0^\infty \psi_{nlm}^*(r, \theta, \phi) \psi_{nlm}(r, \theta, \phi) r^2 \sin\theta \, dr \, d\theta \, d\phi = \delta_{nn'} \delta_{ll'} \delta_{mm'}$$

能级简并：$n = n_r + l + 1$，能级简并度 $f_n = \sum_{l=0}^{n-1} (2l+1) = n^2$。

### 径向位置概率分布

在 $(r, r+dr)$ 内概率为：

$$r^2 dr \int_0^{2\pi} \int_0^\pi |\psi_{nlm}(r, \theta, \phi)|^2 \sin\theta \, d\theta \, d\phi = r^2 |R_{nl}(r)|^2 dr = |u_{nl}(r)|^2 dr$$

$u_{nl}(r)$ 的节点数为 $n_r = n - l - 1$。$n_r = 0$ 的态称为圆轨道，$|u_{nl}(r)|^2$ 极大值位置为 $r_n = n^2 a_0$，其中 $a_0 = \frac{4\pi\varepsilon_0 \hbar^2}{M e^2} = 0.529 \times 10^{-10}\,\text{m}$（玻尔半径）。

守恒量与能级简井度
GUNIVERSITY OF SCIENCEANDT
OF SCIENCE AND TECHNOLOGY
R.China 中国．武汉 T

A.B为厄米算符（乡＜41A-i<41B)(§A14>+iB14>)

HH华中科技大学 NGUNIVERSITY OF SCIENCE ANDI

列向量e:'的线性组
Ssi S22…Sok…
Sp+S2-Sk…)

(ei,ei)(t.e)(ei.ep)…

zhnh华中科技大学