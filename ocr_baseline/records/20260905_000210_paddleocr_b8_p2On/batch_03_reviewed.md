# 科技

## 常见对易恒等式

④常见对易恒等式

- $[A，B]=-[B，A]$
- $[A，B+C]=[A，B]+[A，C]$
- $[A，BC]=[A，B]C+B[A，C]$
- $[AB，C]=A[B，C]+[A，C]B$
- $[A，B+C]+[B，A+C]+[C，A+B]=0$
- $[A，[B，C]]+[B，[C，A]]+[C，[A，B]]=0$（对称）

## 利用对易关系求解平均值问题

**例1.** 求 $l_x$ 和 $l_y$ 在 $|lm\rangle$ 下的平均值。

$l_z|lm\rangle = m\hbar|lm\rangle$，$[l_y，l_z]=i\hbar l_x$，$[l_z，l_x]=i\hbar l_y$，从而可用含 $l_z$ 的表达式表出 $l_x$、$l_y$。

$\bar{l_x} = \langle lm|l_x|lm\rangle = \langle lm|\frac{1}{i\hbar}[l_y，l_z]|lm\rangle = \frac{1}{i\hbar}[\langle lm|l_y l_z|lm\rangle - \langle lm|l_z l_y|lm\rangle]$

$l_z|lm\rangle = m\hbar|lm\rangle$，$m$ 为实数，则 $\langle lm|l_z = m\hbar\langle lm|$，$\therefore \bar{l_x} = \frac{1}{i\hbar}[m\hbar\langle lm|l_y|lm\rangle - m\hbar\langle lm|l_y|lm\rangle]$

$= m\langle lm|l_y|lm\rangle - m\langle lm|l_y|lm\rangle \therefore \bar{l_x} = 0$

**例2.** $|lm\rangle$ 为 $l^2$，$l_z$ 的共同本征态，求 $\bar{l_x^2}$，$\bar{l_y^2}$。

$\bar{l_x^2} = \langle lm|l_x^2|lm\rangle = \langle lm|\frac{1}{2}(l_+ l_- + l_- l_+)|lm\rangle = \frac{1}{2}[l(l+1) - m^2]\hbar^2$，$\bar{l_y^2} = \langle lm|l_y^2|lm\rangle = \langle lm|\frac{1}{2}(l_+ l_- - l_- l_+)|lm\rangle = \frac{1}{2}[l(l+1) - m^2]\hbar^2$

$l_x^2 = \frac{1}{4}(l_+ + l_-)^2 = \frac{1}{4}(l_+^2 + l_+ l_- + l_- l_+ + l_-^2)$，$l_y^2 = -\frac{1}{4}(l_+ - l_-)^2 = -\frac{1}{4}(l_+^2 - l_+ l_- - l_- l_+ + l_-^2)$

$l_y l_z - l_z l_y = (l_z l_y - l_y l_z) + 2l_y l_z - l_z l_y = [l_y，l_z] + 2l_y l_z - l_z l_y$

$l_x^2 + l_y^2 = \frac{1}{2}(l_+ l_- + l_- l_+) = l^2 - l_z^2 = l(l+1)\hbar^2 - m^2\hbar^2 = \hbar^2[l(l+1) - m^2]$

设 $\bar{l_x^2} = \bar{l_y^2} = \frac{1}{2}\hbar^2[l(l+1) - m^2]$

**方法：** 将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

# 不确定度关系的严格证明

任意给定力学量 $A$ 和 $B$，对应的米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \Delta B \ge \frac{1}{2}|\langle[\hat{A},\hat{B}]\rangle|$$

其中 $\langle A,B\rangle=\langle \hat{A}\hat{B}\rangle$ 对成立，$\Delta A=\hat{A}-\langle A\rangle$，$\Delta B=\hat{B}-\langle B\rangle$，也即

$$[\hat{A},\hat{B}]=[\Delta A+\langle A\rangle,\Delta B+\langle B\rangle]=(\Delta A+\langle A\rangle)(\Delta B+\langle B\rangle)-(\Delta B+\langle B\rangle)(\Delta A+\langle A\rangle)=[\Delta A,\Delta B]$$

$$\Delta A=\sqrt{\langle A^2\rangle-\langle A\rangle^2}=\sqrt{\langle(\hat{A}-\langle A\rangle)^2\rangle},\quad \Delta B=\sqrt{\langle B^2\rangle-\langle B\rangle^2}$$

要证也即 $\langle(\hat{A}-\langle A\rangle)^2\rangle\langle(\hat{B}-\langle B\rangle)^2\rangle\ge \frac{1}{4}|\langle[\hat{A}-\langle A\rangle,\hat{B}-\langle B\rangle]\rangle|^2$

令 $x=\hat{A}-\langle A\rangle$，$r=\hat{B}-\langle B\rangle$，要证变为：$\langle x^2\rangle\langle r^2\rangle\ge \frac{1}{4}|\langle[x,r]\rangle|^2$，联想 $b^2\ge 4ac$。

考虑 $|\phi\rangle=(\lambda \hat{A}+i\hat{B})|\psi\rangle$，$\langle\phi|\phi\rangle\ge 0$，$\langle(\lambda\hat{A}+i\hat{B})\psi|(\lambda\hat{A}+i\hat{B})\psi\rangle=(\lambda\langle\psi|\hat{A}-i\langle\psi|\hat{B})(\lambda\hat{A}|\psi\rangle+i\hat{B}|\psi\rangle)$

$=(\lambda\langle\psi|\hat{A}-i\langle\psi|\hat{B})(\lambda\hat{A}|\psi\rangle+i\hat{B}|\psi\rangle)$，$\hat{A},\hat{B}$ 为厄米算符

$=\lambda^2\langle\psi|\hat{A}^2|\psi\rangle+\langle\psi|\hat{B}^2|\psi\rangle+i\lambda(\langle\psi|\hat{A}\hat{B}|\psi\rangle-\langle\psi|\hat{B}\hat{A}|\psi\rangle)=\lambda^2\langle A^2\rangle+\langle B^2\rangle+i\lambda\langle[\hat{A},\hat{B}]\rangle$

$\because \forall\lambda,\ \langle\phi|\phi\rangle\ge 0$，$\therefore (\langle i[\hat{A},\hat{B}]\rangle)^2\le 4\langle A^2\rangle\cdot\langle B^2\rangle$，即 $\langle A^2\rangle\langle B^2\rangle\ge \frac{1}{4}|\langle[\hat{A},\hat{B}]\rangle|^2$，$\therefore \langle x^2\rangle\langle r^2\rangle\ge \frac{1}{4}|\langle[x,r]\rangle|^2$

$$\Rightarrow \Delta A\Delta B\ge \frac{1}{2}|\langle[\hat{A},\hat{B}]\rangle|$$

**对任意力学量 $A$、$B$ 及任意量子态 $|\psi\rangle$，若 $A$ 与 $B$ 不对易（即 $[\hat{A},\hat{B}]\neq 0$），则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 $A$ 与 $B$ 不能同时测定。**

## 共同本征函数

设 $\hat{A}\psi_a=a\psi_a$，$\hat{B}\psi_b=b\psi_b$。若 $[\hat{A},\hat{B}]\neq 0$，则 $\psi_a$ 不是 $\hat{B}$ 的本征函数，$\psi_b$ 不是 $\hat{A}$ 的本征函数。

若 $[\hat{A},\hat{B}]=0$，则可能存在 $\psi$，使 $\hat{A}\psi=a\psi$，$\hat{B}\psi=b\psi$，此时称 $\psi$ 为 $A$ 和 $B$ 的共同本征函数。

**定理：** 设 $\hat{A}|k\rangle=a_k|k\rangle$，另有 $\hat{B}$，若 $[\hat{A},\hat{B}]=0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $A$ 和 $B$ 拥有共同本征态。

证明：$[\hat{A},\hat{B}]=0\Rightarrow \hat{A}\hat{B}=\hat{B}\hat{A}$，$\hat{B}\hat{A}|k\rangle=\hat{B}\cdot a_k|k\rangle=a_k\hat{B}|k\rangle$。则 $\hat{A}(\hat{B}|k\rangle)=a_k(\hat{B}|k\rangle)$，$\therefore \hat{B}|k\rangle$ 也是 $A$ 属于本征值 $a_k$ 的本征态，故 $\hat{B}|k\rangle$ 与 $|k\rangle$ 是一个量子态，即 $\hat{B}|k\rangle=b_k|k\rangle$。$A$、$B$ 拥有共同本征态 $|k\rangle$。

**例：** $\psi(\vec{r})=(2\pi\hbar)^{-\frac{3}{2}}e^{\frac{i}{\hbar}\vec{p}\cdot\vec{r}}$ 是 $\hat{p}_x,\hat{p}_y,\hat{p}_z$ 的共同本征函数，本征值为 $p_x,p_y,p_z$，$\hat{p}\psi(\vec{r})=\vec{p}\psi(\vec{r})$。

## 厄米算符本征值与本征态的特性

**转置算符**：对算符 $\hat{A}$ 和 $\hat{A}^T$，若 $\langle \phi|\hat{A}|\psi\rangle = \langle \psi|\hat{A}^T|\phi\rangle$，则称 $\hat{A}$ 和 $\hat{A}^T$ 互为彼此的转置算符。

**共轭算符**：对算符 $\hat{A}$ 的每一矩阵元取复共轭，得到 $\hat{A}^*$ 为 $\hat{A}$ 的共轭算符。

**厄米算符**：$\hat{A} = \hat{A}^\dagger = (\hat{A}^T)^*$，则称 $\hat{A}$ 为厄米算符。

**定理**：厄米算符 $\hat{A}$ 在任意量子态下的平均值 $\langle A\rangle$ 为实数，且 $\hat{A}^2$ 的平均值 $\langle A^2\rangle \ge 0$。

证明：
$$\langle \phi|\hat{A}|\phi\rangle = \langle \phi|\hat{A}^\dagger|\phi\rangle = \langle \phi|\hat{A}|\phi\rangle^* = \langle \phi|\hat{A}|\phi\rangle$$
∴ $\langle A\rangle = \langle A\rangle^*$，$\langle A\rangle$ 为实数。

或：$\langle \phi|\hat{A}^\dagger|\phi\rangle = \langle \hat{A}\phi|\phi\rangle$，$\langle \phi|\hat{A}|\phi\rangle = \langle \hat{A}^\dagger\phi|\phi\rangle$，$\hat{A} = \hat{A}^\dagger = \hat{A}^*$，$\langle A\rangle$ 为实数。

$$\langle \phi|\hat{A}^2|\phi\rangle = \langle \phi|\hat{A}\hat{A}|\phi\rangle = \langle \hat{A}\phi|\hat{A}\phi\rangle = \langle \Phi|\Phi\rangle \ge 0, \quad |\Phi\rangle = \hat{A}|\phi\rangle$$
∴ $\langle A^2\rangle \ge 0$。

### 厄米算符本征值的实数性

设 $\hat{F}|k\rangle = \lambda_k|k\rangle$，则
$$\langle k|\hat{F}|k\rangle = \langle k|\lambda_k|k\rangle = \lambda_k\langle k|k\rangle = \lambda_k$$
又 $\langle k|\hat{F}|k\rangle = \langle k|\hat{F}^\dagger|k\rangle = \langle k|\hat{F}|k\rangle^* = \lambda_k^*$，且 $\langle k|k\rangle = 1$，
∴ $\lambda_k = \lambda_k^*$，即 $\lambda_k$ 为实数。

### 厄米算符本征态的正交性与完备性、封闭性

**① 厄米算符属于不同本征值的本征态必然正交**（对不同 $|k\rangle$ 可能有不同的 $\lambda_k$）

设 $\hat{F}|k\rangle = \lambda_k|k\rangle$，$\hat{F}|k'\rangle = \lambda_{k'}|k'\rangle$。
$$\langle k'|\hat{F}|k\rangle = \lambda_k\langle k'|k\rangle$$
$$\langle k'|\hat{F}|k\rangle = \langle k|\hat{F}|k'\rangle^* = \langle k|\hat{F}^\dagger|k'\rangle = \langle k|\hat{F}|k'\rangle = \lambda_{k'}\langle k|k'\rangle = \lambda_{k'}\langle k'|k\rangle$$
又 $\lambda_k$ 为实数，$\lambda_k = \lambda_k^*$，
∴ $\lambda_k\langle k'|k\rangle = \lambda_{k'}\langle k'|k\rangle$，而 $\lambda_k \ne \lambda_{k'}$，
∴ $\langle k'|k\rangle = 0$，即 $|k\rangle$ 与 $|k'\rangle$ 正交。

**② 本征态的完备性**

$\hat{P}_k = |k\rangle\langle k|$ 为投影算符，$\hat{P}_k = \hat{P}_k^\dagger$。

若对任意 $|\psi\rangle$，有 $\hat{P}|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = |\psi\rangle$，则称基矢 $|k\rangle$ 具有完备性（任意 $|\psi\rangle$ 可按 $|k\rangle$ 展开）。

记 $C_k = \langle k|\psi\rangle$，则 $|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = \sum_k C_k|k\rangle$，$C_k$ 为用 $|k\rangle$ 将 $|\psi\rangle$ 做展开时的展开系数。

**定理**：哈密顿算符 $\hat{H}$ 为厄米算符，满足本征方程 $\hat{H}|k\rangle = E_k|k\rangle$。对体系的任一归一化态 $|\phi\rangle$，若 $\langle \hat{H}\rangle = \langle \phi|\hat{H}|\phi\rangle$ 有下界（总大于某常数）但无上界，则 $\hat{H}$ 的本征态 $|k\rangle$ 的集合构成体系的一个**完备集**，即体系的任一量子态 $|\psi\rangle$ 可用 $|k\rangle$ 来展开。

### 本征态的封闭性

若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = 1$，称为本征态或基矢 $|k\rangle$ 的**封闭性**；其中 $\hat{P}_k = |k\rangle\langle k|$，$\sum_k \hat{P}_k = 1$ 称为投影算符的封闭性。

**完备性与封闭性**：强调重点不同。完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开；封闭性指数学上封闭性方程 $\sum_k |k\rangle\langle k| = 1$ 成立，两者相互依存。

**例**：设体系的能量本征方程为 $\hat{H}|k\rangle = E_k|k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k |k\rangle\langle k|$（本征态具有完备性、封闭性）。

证明：$\hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$，则 $\hat{H}|k\rangle\langle k| = \hat{H}|k\rangle\langle k| = E_k|k\rangle\langle k|$，从而有 $\hat{H} = \sum_k E_k |k\rangle\langle k|$。

---

## 守恒量与能级简并度

### 力学量平均值的时间依赖特性

$\bar{A}(t) = \langle\psi(t)|\hat{A}|\psi(t)\rangle$，薛定谔方程：$i\hbar\frac{\partial}{\partial t}|\psi(t)\rangle = \hat{H}|\psi(t)\rangle$。在左矢空间中：$-i\hbar\frac{\partial}{\partial t}\langle\psi| = \langle\psi|\hat{H}$（$\hbar = 1$）

$\frac{d\bar{A}}{dt} = \frac{\partial}{\partial t}\langle\psi|\hat{A}|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle + \langle\psi|\hat{A}\frac{\partial}{\partial t}|\psi\rangle = -i\langle\psi|\hat{H}\hat{A}|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle + i\langle\psi|\hat{A}\hat{H}|\psi\rangle$

$= \langle\psi|[\hat{A}, \hat{H}]|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle$，若 $\frac{\partial \hat{A}}{\partial t} = 0$（$\hat{A}$ 不显含 $t$）且 $[\hat{A}, \hat{H}] = 0$，则 $\frac{d\bar{A}}{dt} = 0$，$\bar{A}$ 与时间无关。

$\bar{A}$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随时间改变。

### 守恒量

$\bar{A}$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $\hat{A}$ 对应的力学量为体系的一个**守恒量**。

$\frac{\partial \hat{A}}{\partial t} = 0$ 且 $[\hat{A}, \hat{H}] = 0$，$\hat{A}$ 为守恒量。

**定理**：若 $[\hat{F}, \hat{H}] = 0$，$[\hat{G}, \hat{H}] = 0$，但 $[\hat{F}, \hat{G}] \neq 0$，则体系的能级是简并的。（$\hat{F}$、$\hat{G}$ 为守恒量）

证明：$\hat{H}$ 有共同本征函数 $\psi$，$\hat{F}\psi = F\psi$，$\hat{H}\psi = E\psi$。∵ $[\hat{G}, \hat{H}] = 0$，则 $\hat{G}\hat{H}\psi = \hat{H}\hat{G}\psi$，$\hat{H}(\hat{G}\psi) = E(\hat{G}\psi)$。

又 $\hat{F}(\hat{G}\psi) \neq F(\hat{G}\psi)$，则 $\hat{G}\psi$ 不是 $\hat{F}$ 的本征态，∴ $\hat{G}\psi$ 和 $\psi$ 不是一个态，即 $E$ 对应至少两个态，能级简并。

## 表象变换与矩阵力学

设 $F=(A_1,A_2,\cdots,A_n)$ 是一组力学量完全集，$|k\rangle$ 是其共同本征态，其中 $k$ 表征所有量子数。$|k\rangle$ 是正交归一的，满足 $\langle k|m\rangle=\delta_{km}$（$k=m$ 时为 1，$k\neq m$ 时为 0），$|k\rangle$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。$\{|k\rangle\}$ 构成一个表象，可称为 $F$ 表象，$F$ 构成无穷维的希尔伯特空间。量子态是希尔伯特空间中的一个矢量，$|\psi\rangle=a_k|k\rangle$，则 $a_k=\langle k|\psi\rangle$ 为内积，也可视为投影。

### 表象间的转化

$F$ 表象中，$|k\rangle$ 为基矢，$|\psi\rangle=a_k|k\rangle$，$|\psi\rangle$ 在 $F$ 表象中可用系数列向量表示为 $a$。

$a'$ 与 $a$ 的转化实际上是基矢之间的转化。

$|\psi\rangle=a_k|k\rangle=a'_\beta|\beta\rangle$，$|k\rangle=\langle \beta|k\rangle|\beta\rangle$（$|k\rangle$ 按 $|\beta\rangle$ 展开），从而统一基矢为 $|\beta\rangle$。

则 $a'_\beta=a_k\langle\beta|k\rangle$，记 $S_{\beta k}=\langle\beta|k\rangle$，$S$ 为变换矩阵。

**注**：$a'$、$a$ 均为系数列向量，与本征态形式相似但意义完全不同。$|k\rangle$ 在希尔伯特空间中可表示为一个列向量，$|\psi\rangle$ 按 $|k\rangle$ 展开所得系数列为 $a$。

从矢量的角度考虑，$|\psi\rangle$ 可表示为列向量 $e$ 的线性组合。要消去基矢，则基矢之间的变换为 $S$ 矩阵，合系数列。

由正交归一性：
- $\langle k'|k\rangle=\delta_{k'k}$，$\langle k|k\rangle=1$
- $|k\rangle=S_{\beta k}|\beta\rangle$，$\langle k|k\rangle=(S_{\beta k}^*)(S_{\beta k})=1$
- $\langle m|k\rangle=(S_{\beta m}^*)(S_{\beta k})=0 \Rightarrow S^\dagger S=SS^\dagger=I$

**$S$ 为幺正矩阵**。

基矢变换的矩阵形式：
$$(e_1',e_2',\cdots,e_k')=(e_1,e_2,\cdots,e_k)S^\dagger$$

- 从矢量的角度考虑，$|14\rangle$ 是 $e_1,e_2,\cdots,e_k$ 的线性组合。
- $S$ 为幺正矩阵。

基矢变换的矩阵形式：
$$(e_1',e_2',\cdots,e_k')=(e_1,e_2,\cdots,e_k)S^\dagger$$

其中 $S^\dagger$ 为 $S$ 的共轭转置，满足 $S^\dagger S=SS^\dagger=I$。

1701572 华be_大附印刷


F1k>=λk|k>，F|k=λ|K>.<K|F|K>=λ<K|K，<kF|K>=<K|F1K>=<FKK>=λ<K|k>

<41A²14>=<4|AA14>=<41AA14>=<A4|A4>=<4|Φ>≥0，∴A≥0. 1Φ>=A14>

中科技大学

$l_y l_z l_x - l_z = (l - l_y) + l l_x - l_x = [l_y, l_2] + 2 l_y - y_2$