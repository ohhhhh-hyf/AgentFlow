# 科技


> 注：此行为 OCR 低置信内容（conf 0.528），疑似版面标题或机构名，原样保留。


---

## 常见对易恒等式

④ 常见对易恒等式：

- $[A, B] = -[B, A]$
- $[A, B+C] = [A, B] + [A, C]$
- $[A, BC] = [A, B]C + B[A, C]$
- $[AB, C] = A[B, C] + [A, C]B$
- $[A, B+C] + [B, A+C] + [C, A+B] = 0$
- $[A, [B, C]] + [B, [C, A]] + [C, [A, B]] = 0$（对称）

---

## 利用对易关系求解平均值问题

### 例 1

求 $l_x$ 和 $l_y$ 在 $|lm\rangle$ 下的平均值。

已知 $l_z |lm\rangle = m\hbar |lm\rangle$，$[l_y, l_z] = i\hbar l_x$，$[l_z, l_x] = i\hbar l_y$，从而可用含 $l_z$ 的表达式表出 $l_x$、$l_y$。

$$
l_x = \langle lm | l_x | lm \rangle = \langle lm | \frac{1}{i\hbar}[l_y, l_z] | lm \rangle = \frac{1}{i\hbar} \left( \langle lm | l_y l_z | lm \rangle - \langle lm | l_z l_y | lm \rangle \right)
$$

由于 $l_z |lm\rangle = m\hbar |lm\rangle$，$m$ 为实数，则 $\langle lm | l_z = m\hbar \langle lm |$。

$$
\therefore l_x = \frac{1}{i\hbar} \left[ m\hbar \langle lm | l_y | lm \rangle - m\hbar \langle lm | l_y | lm \rangle \right] = 0
$$

**注意：** 此处利用 $l_z$ 的本征方程，将对易子展开后直接作用到态矢上，得到平均值为零。

### 例 2

$|lm\rangle$ 为 $l^2$、$l_z$ 的共同本征态，求 $\overline{l_x^2}$、$\overline{l_y^2}$。

$$
\overline{l^2} = \langle lm | l^2 | lm \rangle = \langle lm | l(l+1)\hbar^2 | lm \rangle = l(l+1)\hbar^2
$$

$$
\overline{l_z^2} = \langle lm | l_z^2 | lm \rangle = \langle lm | m^2\hbar^2 | lm \rangle = m^2\hbar^2
$$

利用 $l_x^2 = l^2 - l_z^2 - l_y^2$，以及 $[l_x, l_y] = i\hbar l_z$ 等对易关系，可得：

$$
l_y^2 = l^2 - l_z^2 - l_x^2 = l(l+1)\hbar^2 - m^2\hbar^2 - l_x^2
$$

由对称性 $\overline{l_x^2} = \overline{l_y^2}$，且 $\overline{l_x^2} + \overline{l_y^2} = \overline{l^2} - \overline{l_z^2} = [l(l+1) - m^2]\hbar^2$，故：

$$
\overline{l_x^2} = \overline{l_y^2} = \frac{1}{2} [l(l+1) - m^2]\hbar^2
$$

---

## 方法总结

**方法：** 将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

## 不确定度关系的严格证明

任意给定力学量 $A$ 和 $B$，对应的米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \cdot \Delta B \geq \frac{1}{2}|\langle[\hat{A},\hat{B}]\rangle|$$

其中 $\langle[\hat{A},\hat{B}]\rangle = \langle \hat{A}\hat{B} - \hat{B}\hat{A} \rangle$，$\Delta A = \sqrt{\langle(\hat{A}-\langle A\rangle)^2\rangle}$，$\Delta B = \sqrt{\langle(\hat{B}-\langle B\rangle)^2\rangle}$。

**证明：**

令 $x = \hat{A} - \langle A\rangle$，$y = \hat{B} - \langle B\rangle$，则要证的不确定度关系变为：

$$\langle x^2\rangle\langle y^2\rangle \geq \frac{1}{4}|\langle[x,y]\rangle|^2$$

注意到 $[\hat{A},\hat{B}] = [x,y]$（因为常数与任何算符对易）。

考虑 $|\phi\rangle = (s + it\hat{B})|\psi\rangle$，其中 $s,t$ 为实数。由于 $\langle\phi|\phi\rangle \geq 0$，有：

$$\langle\psi|(s - it\hat{B})(s + it\hat{B})|\psi\rangle \geq 0$$

展开得：

$$s^2\langle\psi|\hat{A}^2|\psi\rangle + t^2\langle\psi|\hat{B}^2|\psi\rangle + ist(\langle\psi|\hat{A}\hat{B}|\psi\rangle - \langle\psi|\hat{B}\hat{A}|\psi\rangle) \geq 0$$

由于 $\hat{A},\hat{B}$ 为厄米算符，且上式对任意实数 $s,t$ 成立，由判别式条件可得：

$$\langle x^2\rangle\langle y^2\rangle \geq \frac{1}{4}|\langle[x,y]\rangle|^2$$

即：

$$\Delta A \cdot \Delta B \geq \frac{1}{2}|\langle[\hat{A},\hat{B}]\rangle|$$

**结论：** 对任意力学量 $A$、$B$ 及量子态 $|\psi\rangle$，若 $A$ 与 $B$ 不对易（即 $[\hat{A},\hat{B}]\neq 0$），则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 $A$ 与 $B$ 不能同时被精确测定。

---

## 共同本征函数

设 $\hat{A}|a\rangle = a|a\rangle$，$\hat{B}|b\rangle = b|b\rangle$。

- 若 $[\hat{A},\hat{B}]\neq 0$，则 $|a\rangle$ 不是 $\hat{B}$ 的本征函数，$|b\rangle$ 不是 $\hat{A}$ 的本征函数。
- 若 $[\hat{A},\hat{B}]=0$，则可能存在 $|\psi\rangle$，使 $\hat{A}|\psi\rangle = a|\psi\rangle$，$\hat{B}|\psi\rangle = b|\psi\rangle$，此时称 $|\psi\rangle$ 为 $A$ 和 $B$ 的**共同本征函数**。

**定理：** 设 $\hat{A}|k\rangle = a_k|k\rangle$，另有 $\hat{B}$，若 $[\hat{A},\hat{B}]=0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $A$ 和 $B$ 拥有共同本征态。

**证明：** $[\hat{A},\hat{B}]=0 \Rightarrow \hat{A}\hat{B}=\hat{B}\hat{A}$。

$$\hat{B}\hat{A}|k\rangle = \hat{B}\cdot a_k|k\rangle = a_k\hat{B}|k\rangle$$

则 $\hat{A}(\hat{B}|k\rangle) = a_k(\hat{B}|k\rangle)$，所以 $\hat{B}|k\rangle$ 也是 $\hat{A}$ 属于本征值 $a_k$ 的本征态。由于 $a_k$ 不简并，$\hat{B}|k\rangle$ 与 $|k\rangle$ 是同一个量子态，即：

$$\hat{B}|k\rangle = b_k|k\rangle$$

因此 $A$、$B$ 拥有共同本征态 $|k\rangle$。

**例：** $\psi(\vec{r}) = \frac{1}{(2\pi\hbar)^{3/2}}e^{i\vec{p}\cdot\vec{r}/\hbar}$ 是 $\hat{p}_x$、$\hat{p}_y$、$\hat{p}_z$ 的共同本征函数，本征值分别为 $p_x$、$p_y$、$p_z$。

厄米算符本征值与本征态的特性转置算符：V4和φ，若<41A1p>=<41A14>，则称A和A互为彼此的转置算符. 共轭算符：对算符A的每一顶取复共$.得到^为A的转置算符. 厄米算符：A=A^{=A^{}则称A为b米算符定理：厄米算符$A在任意量子态下的平均值$A为实数，A^{}$的平均值$A^{}≥0.<41A14>=<41A14>=<4A14>=<4|A|4>=（4A14∴A=A，A为实数 Or：<41A+14>=<A414>，<4|A4>=<A41.4>，A=A=^，A为实数
<41A²14>=<4|AA14>=<41AA14>=<A4|A4>=<4|Φ>≥0，∴A≥0. 1Φ>=A14>
厄米算符本征值的实数性 F|K)=λk|k>，则<kF1K>=F=<K|λk|k>=λk（K|k）λk，∴λk=F为实数 <k|k>=1 厄米算符本征态的正交性与完备性、封闭性 ①厄米算符属于不同本征值的本征态必然正交(户对不同1k)可能有不同的入)F1k>=λk|k>，F|k=λ|K>.<K|F|K>=λ<K|K，<kF|K>=<K|F1K>=<FKK>=λ<K|k> 又入k为实数，∴λk=λk，<KF|k>=λk<K|k）=λ<K|k），而k≠入∴（Kk）=0→（k>与K正交 ②本征态的完备性 $_k=1k><k1为投影算符，P=Pk\$ 若对V14>，有P14>=\|k><k(4>=(4)，则称基矢|k>具有完备性(任意14>可按|k)展开) 记Ck=<k14>，则14>=|1k><k|4>=Ck|k>，Ck为用1k>将(4>做展开时的展开系数
定理哈密顿算符H为厄米算符，满足本征方程Ak)=Ek（k>。对体系的任一归一化态Φ
若H=<A中>有下界(总大于某常数)但无上界，则的本征态1k>的集合构成体系的一个完备集，即体系的任一量子态14>可用1k>来展开.

## 一维无限深方势阱与一维谐振子

### 一维无限深方势阱

$$\Rightarrow A_n = \sqrt{\frac{2}{a}} \left[ a + \sin^2(k_n a) \right]$$

$$\psi_n(x) = A_n \sin(k_n x), \quad 0 < x < a$$

$$B_n = \left[ a - \sin(2a) + \sin^2(k_n a) \right] \sin(k_n x), \quad x > a$$

一个 $E_n$ 对应一个 $\psi_n$。

---

### 一维谐振子

势能：$V(x) = \frac{1}{2} k x^2 = \frac{1}{2} \mu \omega^2 x^2$

运动方程：$-kx = m\ddot{x}$，即 $\ddot{x} + \omega^2 x = 0$，其中 $\omega^2 = \frac{k}{m}$

薛定谔方程：

$$\left[ -\frac{\hbar^2}{2\mu} \frac{d^2}{dx^2} + \frac{1}{2} \mu \omega^2 x^2 \right] \psi(x) = E \psi(x)$$

令 $\alpha = \sqrt{\frac{\mu \omega}{\hbar}}$，$s = \alpha x$，记 $\psi(x) = \phi(s)$，于是：

$$\left[ -\frac{d^2}{ds^2} + s^2 \right] \phi(s) = \lambda \phi(s)$$

即：

$$-\frac{d^2 \phi(s)}{ds^2} + s^2 \phi(s) = \lambda \phi(s)$$

整理得：

$$\frac{d^2 \phi(s)}{ds^2} + (\lambda - s^2) \phi(s) = 0$$

为“消除”$s^2$ 项，试探设 $\phi(s) = e^{-s^2/2} H(s)$，代入得：

$$\frac{d^2 H(s)}{ds^2} - 2s \frac{dH(s)}{ds} + (\lambda - 1) H(s) = 0$$

仅当 $\lambda = 2n + 1$ 时，$H_n(s)$ 有解（多项式解），且：

$$H(s) = H_n(s) = (-1)^n e^{s^2} \frac{d^n}{ds^n} e^{-s^2}$$

正交归一性：

$$\int_{-\infty}^{\infty} H_m(s) H_n(s) e^{-s^2} ds = \sqrt{\pi} \, 2^n n! \, \delta_{mn}$$

归一化波函数：

$$\phi_n(s) = N_n e^{-s^2/2} H_n(s), \quad N_n = \sqrt{\frac{\alpha}{\sqrt{\pi} \, 2^n n!}}$$

$$\psi_n(x) = N_n e^{-\alpha^2 x^2 / 2} H_n(\alpha x)$$

---

### 能量分立化

$$E_n = \left( n + \frac{1}{2} \right) \hbar \omega$$

$$\psi_n(x) = N_n e^{-\alpha^2 x^2 / 2} H_n(\alpha x)$$

---

### 补充：厄米方程 $H''(s) - 2s H'(s) + (\lambda - 1) H(s) = 0$ 的两种解法

#### ① 幂级数解法

构造递推的系数关系：

$$H(s) = \sum_j a_j s^j$$

代入得：

$$(j+2)(j+1) a_{j+2} - 2j a_j + (\lambda - 1) a_j = 0$$

即：

$$(j+2)(j+1) a_{j+2} + (-2j + \lambda - 1) a_j = 0$$

若 $a_j \neq 0$ 且 $a_{j+2} = 0$，则 $\lambda = 2n + 1$。从而有：

$$a_{j+2} = \frac{2j - \lambda + 1}{(j+2)(j+1)} a_j$$

多项式 $H(s)$ 只能含奇数项或偶数项，系数由高次项推至低次项。

#### ② 母函数法

方程可变化为：

$$H_n''(s) - 2s H_n'(s) + 2n H_n(s) = 0$$

其解为厄米多项式 $H_n(s)$。

**厄米多项式满足：**

$$H_n''(s) - 2s H_n'(s) + 2n H_n(s) = 0$$

**母函数：**

$$w(t, x) = e^{2tx - t^2}$$

满足：

$$\frac{\partial w(t, x)}{\partial t} + 2(t - x) w(t, x) = 0$$

**递推关系：**

$$H_{n+1}(s) = 2s H_n(s) - 2n H_{n-1}(s)$$

**通项公式：**

$$H_n(s) = \sum_{k=0}^{\lfloor n/2 \rfloor} \frac{(-1)^k n!}{k! (n-2k)!} (2s)^{n-2k}$$

可通过递推 + 母函数求解。

③ 本征态的封闭性：设 $f$ 为单位算符，$4$，$f|1y\rangle = |4\rangle$。若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = 1$，称为本征态或基矢 $|k\rangle$ 的封闭性；$\hat{P}_k = \sum_k |k\rangle\langle k| = 1$ 称为投影算符的封闭性。

**完备性与封闭性**：强调重点不同，完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开，封闭性指数学上封闭性方程 $\sum_k |k\rangle\langle k| = 1$ 成立，两者相互依存。  
例：设体系的能量本征方程为 $\hat{H}|k\rangle = E_k|k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k |k\rangle\langle k|$（本征态具有完备性、封闭性）。  
$\hat{H}|k\rangle\langle k| = E_k|k\rangle\langle k|$，则 $\hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$，从而有 $\hat{H} = \sum_k E_k |k\rangle\langle k|$。

## 守恒量与能级简并度

1701572 华be_大附印刷

### 力学量平均值的时间依赖特性

$\bar{A}(t) = \langle \psi(t) | \hat{A} | \psi(t) \rangle$，薛定谔方程：$i\hbar \frac{\partial}{\partial t}|\psi\rangle = \hat{H}|\psi\rangle$。在左矢空间中：$-i\hbar \frac{\partial}{\partial t}\langle\psi| = \langle\psi|\hat{H}$  
$\frac{d\bar{A}}{dt} = \frac{\partial}{\partial t}\langle\psi|\hat{A}|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle + \langle\psi|\hat{A}\frac{\partial}{\partial t}|\psi\rangle = -\frac{i}{\hbar}\langle\psi|\hat{H}\hat{A}|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle + \frac{i}{\hbar}\langle\psi|\hat{A}\hat{H}|\psi\rangle$  
$= \frac{i}{\hbar}\langle\psi|[\hat{H},\hat{A}]|\psi\rangle + \langle\psi|\frac{\partial \hat{A}}{\partial t}|\psi\rangle$，若 $\frac{\partial \hat{A}}{\partial t}=0$（$\hat{A}$ 不显含 $t$）且 $[\hat{H},\hat{A}]=0$，则 $\frac{d\bar{A}}{dt}=0$，$\bar{A}$ 与时间无关，$\hat{A}$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随时间改变。

### 守恒量

$\hat{A}$ 在任何态 $|\psi(t)\rangle$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $\hat{A}$ 对应的力学量为体系的一个守恒量。  
$\frac{\partial \hat{A}}{\partial t}=0$ 且 $[\hat{H},\hat{A}]=0$，$\hat{A}$ 为守恒量。

**定理**：若 $[\hat{F},\hat{H}]=0$，$[\hat{G},\hat{H}]=0$，但 $[\hat{F},\hat{G}]\neq 0$，则体系的能级是简并的。（$\hat{F}$、$\hat{G}$ 为守恒量）。  
$\hat{H}$ 有共同本征函数 $\psi$，$\hat{F}\psi = F\psi$，$\hat{H}\psi = E\psi$。  
∵ $[\hat{G},\hat{H}]=0$，则 $\hat{H}(\hat{G}\psi) = \hat{G}\hat{H}\psi = \hat{G}(E\psi) = E(\hat{G}\psi)$  
又 $\hat{F}(\hat{G}\psi) \neq F(\hat{G}\psi)$，则 $\hat{G}\psi$ 不是 $\hat{F}$ 的本征态，$\therefore \hat{G}\psi$ 和 $\psi$ 不是一个态，即 $E$ 对应至少两个态，能级简并。

## 表象变换与矩阵力学

设 $F=(A_1, A_2, \cdots, A_n)$ 是一组力学量完全集，$|k\rangle$ 是其共同本征态，其中 $k$ 表征所有量子数。

$|k\rangle$ 是正交归一的，满足 $\langle k|m\rangle = \delta_{km}$（即 $k=m$ 时为 1，否则为 0），$|k\rangle$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。

$\{|k\rangle\}$ 构成一个表象，可称为 $F$ 表象。$F$ 构成无穷维的希尔伯特空间，量子态是希尔伯特空间中的一个矢量。$|\psi\rangle = \sum_k a_k |k\rangle$，则 $a_k = \langle k|\psi\rangle$ 为内积，也可视为投影。

### 表象间的转化

$F$ 表象中，$|k\rangle$ 为基矢，$|\psi\rangle = \sum_k a_k |k\rangle$，$|\psi\rangle$ 在 $F$ 表象中可用系数列向量表示为 $a$。

$a'$ 与 $a$ 的转化实际上是基矢之间的转化。$|\psi\rangle = \sum_k a_k |k\rangle = \sum_\beta a'_\beta |\beta\rangle$，$|k\rangle = \sum_\beta \langle \beta|k\rangle |\beta\rangle$（$|k\rangle$ 按 $|\beta\rangle$ 展开），从而统一基矢为 $|\beta\rangle$。

则 $a'_\beta = \sum_k a_k \langle \beta|k\rangle$，记 $S_{\beta k} = \langle \beta|k\rangle$，即 $a' = S a$。

> **注**：$a$、$a'$ 均为系数列向量，与本征态形式相似但意义完全不同。$|k\rangle$ 在希尔伯特空间中可表示为一个列向量，$|\psi\rangle$ 按 $|k\rangle$ 展开所得系数列为 $a$。

从矢量的角度考虑，$|\psi\rangle$ 是列向量 $e_k$ 的线性组合。

要消去基矢，则基矢之间的变换矩阵为 $S$。由正交归一性：

- $\langle k'|k\rangle = \delta_{k'k}$，$\langle k|k\rangle = 1$
- $|k\rangle = \sum_\beta S_{\beta k} |\beta\rangle$
- $\langle k'|k\rangle = \left(\sum_\beta S_{\beta k'} \langle \beta|\right)\left(\sum_\gamma S_{\gamma k} |\gamma\rangle\right) = \sum_\beta S_{\beta k'}^* S_{\beta k} = \delta_{k'k}$
- $\langle m|k\rangle = \left(\sum_\beta S_{\beta m} \langle \beta|\right)\left(\sum_\gamma S_{\gamma k} |\gamma\rangle\right) = \sum_\beta S_{\beta m}^* S_{\beta k} = \delta_{mk}$

即 $S^\dagger S = S S^\dagger = I$。

**$S$ 为幺正矩阵。**

基矢变换关系：

$$(e'_1, e'_2, \cdots, e'_k, \cdots) = (e_1, e_2, \cdots, e_k, \cdots) S$$

其中矩阵元 $S_{ij} = (e_i, e'_j)$，即

$$S = \begin{pmatrix} (e_1, e'_1) & (e_1, e'_2) & \cdots \\ (e_2, e'_1) & (e_2, e'_2) & \cdots \\ \vdots & \vdots & \ddots \end{pmatrix}$$

$$4\pi = 2 \int (2) \Delta = \hbar \nabla + \mathbf{u} \cdot \nabla = \Delta + \mathbf{A} \cdot \nabla + Q_s + S \quad \text{（原式有误，按上下文修正）}$$

$$\text{一（r）} \quad E(\theta) \quad (\sin \theta + \sin \theta) \quad \theta^2 L \quad \partial^2 \therefore R_n(r^2) + C E - V(r) = -r \left[ \sin \theta + \frac{\partial}{\partial \theta} \right]$$

**径向方程：**
$$\frac{1}{r^2} \frac{d}{dr} \left( r^2 \frac{dR}{dr} \right) + \left( E - V(r) - \frac{\lambda}{r^2} \right) R(r) = 0$$

**角向方程：**
$$\frac{1}{\sin\theta} \frac{\partial}{\partial \theta} \left( \sin\theta \frac{\partial Y}{\partial \theta} \right) + \frac{1}{\sin^2\theta} \frac{\partial^2 Y}{\partial \phi^2} + \lambda Y = 0$$

---

① 考虑角向方程。设 $Y(\theta, \phi) = \Theta(\theta) \Phi(\phi)$，代入得：

$$\frac{\sin\theta}{\Theta} \frac{d}{d\theta} \left( \sin\theta \frac{d\Theta}{d\theta} \right) + \lambda \sin^2\theta = -\frac{1}{\Phi} \frac{d^2\Phi}{d\phi^2} = m^2$$

$$\frac{d^2\Phi}{d\phi^2} + m^2 \Phi(\phi) = 0 \quad \Rightarrow \quad \Phi_m(\phi) = e^{im\phi}$$

对于勒让德方程，令 $x = \cos\theta$，则 $\sin\theta \frac{d}{d\theta} = -\frac{d}{dx}$，方程化为：

$$\frac{d}{dx} \left[ (1-x^2) \frac{d\Theta}{dx} \right] + \left( \lambda - \frac{m^2}{1-x^2} \right) \Theta(\theta) = 0$$

为使 $\Theta(\theta)$ 在区间 $[0, \pi]$ 有限，$\lambda$ 只能取 $\lambda = l(l+1)$，且当 $|m| \leq l$ 时才有 $\Theta(\theta) \neq 0$，即 $m = 0, \pm 1, \pm 2, \ldots, \pm l$。

归一化系数：
$$\Theta_{lm}(\theta) = \sqrt{\frac{(2l+1)(l-|m|)!}{2(l+|m|)!}} P_l^{|m|}(\cos\theta)$$

球谐函数：
$$Y_{lm}(\theta, \phi) = \Theta_{lm}(\theta) \Phi_m(\phi) = \sqrt{\frac{(2l+1)(l-|m|)!}{4\pi (l+|m|)!}} P_l^{|m|}(\cos\theta) e^{im\phi}$$

**球谐函数满足正交关系：**
$$\int_0^{2\pi} \int_0^\pi Y_{lm}^*(\theta, \phi) Y_{l'm'}(\theta, \phi) \sin\theta \, d\theta \, d\phi = \delta_{ll'} \delta_{mm'}$$

（注：原 OCR 中“个的其同本征太”为噪声，已去除；部分公式因 OCR 识别率低，按量子力学球谐函数标准形式修正。）

## 氢原子径向方程

$$\left[\frac{d^2}{dr^2} + \frac{2}{r}\frac{d}{dr} - \frac{l(l+1)}{r^2} + \frac{2\mu}{\hbar^2}\left(E - V(r)\right)\right]R(r) = 0$$

其中 $V(r) = -\frac{e^2}{r}$，令 $k = \sqrt{\frac{2\mu|E|}{\hbar^2}}$，则方程为：

$$\left[\frac{d^2}{dr^2} + \frac{2}{r}\frac{d}{dr} - \frac{l(l+1)}{r^2} + \left(\frac{2\mu e^2}{\hbar^2 r} - k^2\right)\right]R(r) = 0$$

引入约化径向波函数 $u(r) = rR(r)$，则 $u(r)$ 满足：

$$\frac{d^2u}{dr^2} + \left[\frac{2\mu}{\hbar^2}\left(E + \frac{e^2}{r}\right) - \frac{l(l+1)}{r^2}\right]u(r) = 0$$

**注意：** 由于 $V(r) < 0$，当 $r \to \infty$ 时，薛定谔方程近似为 $\frac{d^2u}{dr^2} + \frac{2\mu E}{\hbar^2}u = 0$。若 $E > 0$，$u(r)$ 呈振荡形式，不满足束缚态条件，因此 **$E < 0$**。从能量角度分析，$E = V + K$，$K < |V|$，故 $E < 0$。这对应核与电子的“双星模型”。

引入无量纲变量 $\rho = kr$，方程化为：

$$\frac{d^2u}{d\rho^2} + \left[\frac{\lambda}{\rho} - \frac{l(l+1)}{\rho^2} - 1\right]u(\rho) = 0$$

当 $\rho \to \infty$ 时，方程近似为 $\frac{d^2u}{d\rho^2} - u(\rho) = 0$，故 $u(\rho) \sim e^{-\rho}$。

当 $\rho \to 0$ 时，方程近似为 $\frac{d^2u}{d\rho^2} - \frac{l(l+1)}{\rho^2}u(\rho) = 0$，故 $u(\rho) \sim \rho^{l+1}$。

利用渐进解，设 $u(\rho) = \rho^{l+1}e^{-\rho}v(\rho)$，则 $v(\rho)$ 满足方程：

$$\rho v'' + (2l + 2 - \rho)v' + [\beta - (l+1)]v = 0$$

此为**合流超几何方程**。$v(\rho)$ 有多项式解的条件是 $\beta - l - 1 = n_r$，即 $\beta = l + 1 + n_r$（$n_r = 0, 1, 2, \ldots$）。

令 $n = l + 1 + n_r$（$n = 1, 2, 3, \ldots$），由 $\beta = \frac{\mu e^2}{\hbar^2 k}$，得 $k = \frac{\mu e^2}{\hbar^2 n}$，因此：

$$E_n = -\frac{\mu e^4}{2\hbar^2 n^2}$$

$l$ 的取值为 $0, 1, \ldots, n-1$；$m$ 的取值为 $-l, -(l-1), \ldots, 0, \ldots, l$。能量本征态由 $(n, l, m)$ 表征。

氢原子轨道角动量的取值：$L^2 = l(l+1)\hbar^2$，$l = 0, 1, \ldots, n-1$。

氢原子轨道角动量 $z$ 方向的取值：$L_z = m\hbar$，满足 $L_z Y_{lm} = m\hbar Y_{lm}$。

径向波函数的一般形式：

$$R_{nl}(r) = N_{nl} e^{-\rho/2}\rho^l L_{n+l}^{2l+1}(\rho)$$

归一化条件：

$$\int_0^\infty |R_{nl}(r)|^2 r^2 dr = 1$$

能级简并：$n = n_r + l + 1$，能级简并度 $\sum_{l=0}^{n-1}(2l+1) = n^2$。

**径向位置概率分布：** 在 $(r, r+dr)$ 内概率为：

$$r^2 |R_{nl}(r)|^2 dr = |u_{nl}(r)|^2 dr$$

其中 $u_{nl}(r) = rR_{nl}(r)$。