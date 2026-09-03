# 常见对易恒等式

$$[A,B] = -[B,A]$$

$$[A,B+C] = [A,B] + [A,C]$$

$$[A,BC] = [A,B]C + B[A,C]$$

$$[AB,C] = A[B,C] + [A,C]B$$

$$[A,[B,C]] + [B,[C,A]] + [C,[A,B]] = 0 \quad \text{（Jacobi 恒等式）}$$

$$[A,B+C] + [B,A+C] + [C,A+B] = 0$$

---

## 利用对易关系求解平均值问题

**例1.** 求 $\hat{L}_x$ 和 $\hat{L}_y$ 在 $|l m\rangle$ 下的平均值。

已知 $\hat{L}_z |l m\rangle = m\hbar |l m\rangle$，$[\hat{L}_y, \hat{L}_z] = i\hbar \hat{L}_x$，$[\hat{L}_z, \hat{L}_x] = i\hbar \hat{L}_y$，从而可用含 $\hat{L}_y$ 的表达式表出 $\hat{L}_x$。

$$\langle l m | \hat{L}_x | l m \rangle = \frac{1}{i\hbar} \langle l m | [\hat{L}_y, \hat{L}_z] | l m \rangle = \frac{1}{i\hbar} \left[ \langle l m | \hat{L}_y \hat{L}_z | l m \rangle - \langle l m | \hat{L}_z \hat{L}_y | l m \rangle \right]$$

由于 $\hat{L}_z |l m\rangle = m\hbar |l m\rangle$，$m$ 为实数，则 $\langle l m | \hat{L}_z = m\hbar \langle l m |$，代入得：

$$\langle l m | \hat{L}_x | l m \rangle = \frac{1}{i\hbar} \left[ m\hbar \langle l m | \hat{L}_y | l m \rangle - m\hbar \langle l m | \hat{L}_y | l m \rangle \right] = 0$$

同理 $\langle \hat{L}_y \rangle = 0$。

**例2.** $|l m\rangle$ 为 $(\hat{L}^2, \hat{L}_z)$ 的共同本征态，求 $\overline{\hat{L}_x^2}$、$\overline{\hat{L}_y^2}$。

$$\overline{\hat{L}_x^2} = \langle l m | \hat{L}_x^2 | l m \rangle = \langle l m | (\hat{L}^2 - \hat{L}_z^2) | l m \rangle = l(l+1)\hbar^2 - m^2\hbar^2$$

利用 $\hat{L}_x = \frac{1}{i\hbar}[\hat{L}_y, \hat{L}_z]$ 等对易关系，可得：

$$\overline{\hat{L}_x^2} = \overline{\hat{L}_y^2} = \frac{1}{2} \left[ l(l+1) - m^2 \right] \hbar^2$$

> **方法**：将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

---

# 不确定度关系的严格证明

任意给定力学量 $A$ 和 $B$，对应的厄米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \cdot \Delta B \geq \frac{1}{2} \left| \langle [\hat{A}, \hat{B}] \rangle \right|$$

其中 $\langle [\hat{A}, \hat{B}] \rangle = \langle \psi | [\hat{A}, \hat{B}] | \psi \rangle$ 对 $\forall |\psi\rangle$ 成立，$\Delta A = \hat{A} - \bar{A}$，$\Delta B = \hat{B} - \bar{B}$。

$$[\hat{A}, \hat{B}] = [\Delta A + \bar{A}, \Delta B + \bar{B}] = (\Delta A + \bar{A})(\Delta B + \bar{B}) - (\Delta B + \bar{B})(\Delta A + \bar{A}) = [\Delta A, \Delta B]$$

$$\Delta A = \sqrt{\overline{(\hat{A} - \bar{A})^2}}, \quad \Delta B = \sqrt{\overline{(\hat{B} - \bar{B})^2}}$$

要证也即 $\overline{(\hat{A} - \bar{A})^2} \cdot \overline{(\hat{B} - \bar{B})^2} \geq \frac{1}{4} \left| \langle [\hat{A} - \bar{A}, \hat{B} - \bar{B}] \rangle \right|^2$。

令 $\hat{X} = \hat{A} - \bar{A}$，$\hat{Y} = \hat{B} - \bar{B}$，要证变为：$\overline{X^2} \cdot \overline{Y^2} \geq \frac{1}{4} |\langle [\hat{X}, \hat{Y}] \rangle|^2$。联想 $b^2 \geq 4ac$。

考虑 $|\phi\rangle = (\xi \hat{X} + i\eta \hat{Y})|\psi\rangle$，$\langle \phi | \phi \rangle \geq 0$：

$$\langle \psi | (\xi \hat{X} - i\eta \hat{Y})(\xi \hat{X} + i\eta \hat{Y}) | \psi \rangle \geq 0$$

$\hat{X}$、$\hat{Y}$ 为厄米算符：

$$= \xi^2 \langle \psi | \hat{X}^2 | \psi \rangle + \eta^2 \langle \psi | \hat{Y}^2 | \psi \rangle + i\xi\eta \left( \langle \psi | \hat{X}\hat{Y} | \psi \rangle - \langle \psi | \hat{Y}\hat{X} | \psi \rangle \right)$$

$$= \xi^2 \overline{X^2} + \eta^2 \overline{Y^2} + i\xi\eta \langle [\hat{X}, \hat{Y}] \rangle \geq 0$$

由判别式 $\Delta \leq 0$，即 $\left( i\langle [\hat{X}, \hat{Y}] \rangle \right)^2 \leq 4 \overline{X^2} \cdot \overline{Y^2}$，即 $\overline{X^2} \cdot \overline{Y^2} \geq \frac{1}{4} |\langle [\hat{X}, \hat{Y}] \rangle|^2$。

$$\Rightarrow \Delta A \cdot \Delta B \geq \frac{1}{2} |\langle [\hat{A}, \hat{B}] \rangle|$$

> **结论**：对任意力学量 $A$、$B$，任意量子态 $|\psi\rangle$，若 $A$ 与 $B$ 不对易即 $[\hat{A}, \hat{B}] \neq 0$，则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 **$A$ 与 $B$ 不能同时测定**。

---

## 共同本征函数

设 $\hat{A}\psi_A = A\psi_A$，$\hat{B}\psi_B = B\psi_B$。若 $[\hat{A}, \hat{B}] \neq 0$，则 $\psi_A$ 不是 $\hat{B}$ 的本征函数，$\psi_B$ 不是 $\hat{A}$ 的本征函数。

若 $[\hat{A}, \hat{B}] = 0$，则可能存在 $\psi$，使 $\hat{A}\psi = A\psi$，$\hat{B}\psi = B\psi$。此时称 $\psi$ 为 $A$ 和 $B$ 的**共同本征函数**。

**定理**：设 $\hat{A}|k\rangle = a_k |k\rangle$，另有 $\hat{B}$，若 $[\hat{A}, \hat{B}] = 0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $A$ 和 $B$ 拥有共同本征态。

**证明**：$[\hat{A}, \hat{B}] = 0 \Rightarrow \hat{A}\hat{B} = \hat{B}\hat{A}$。$\hat{B}\hat{A}|k\rangle = \hat{B} \cdot a_k |k\rangle = a_k \hat{B}|k\rangle$。则 $\hat{A}(\hat{B}|k\rangle) = a_k (\hat{B}|k\rangle)$，即 $\hat{B}|k\rangle$ 也是 $A$ 属于本征值 $a_k$ 的本征态。故 $\hat{B}|k\rangle$ 与 $|k\rangle$ 是同一个态，即 $\hat{B}|k\rangle = b_k |k\rangle$。$\Rightarrow A$、$B$ 拥有共同本征态 $|k\rangle$。

**例**：$\psi_{\vec{p}}(\vec{r}) = \frac{1}{(2\pi\hbar)^{3/2}} e^{i\vec{p}\cdot\vec{r}/\hbar}$ 为 $\hat{p}_x, \hat{p}_y, \hat{p}_z$ 的共同本征函数，本征值为 $p_x, p_y, p_z$。

$$\hat{p}_x \psi_{\vec{p}}(\vec{r}) = p_x \psi_{\vec{p}}(\vec{r})$$

---

# 厄米算符本征值与本征态的特性

**转置算符**：对 $\forall \psi$ 和 $\phi$，若 $\langle \psi | \hat{A} | \phi \rangle = \langle \phi | \hat{A}^T | \psi \rangle$，则称 $\hat{A}$ 和 $\hat{A}^T$ 互为彼此的转置算符。

**共轭算符**：对算符 $\hat{A}$ 的每一项取复共轭，得到 $\hat{A}^*$ 为 $\hat{A}$ 的转置算符。

**厄米算符**：$\hat{A} = \hat{A}^\dagger = \hat{A}^{*T}$，则称 $\hat{A}$ 为厄米算符。

**定理**：厄米算符 $\hat{A}$ 在任意量子态下的平均值 $\bar{A}$ 为实数，$\overline{A^2}$ 的平均值 $\geq 0$。

$$\langle \psi | \hat{A} | \psi \rangle = \langle \psi | \hat{A}^\dagger | \psi \rangle = \langle \psi | \hat{A}^* | \psi \rangle = \langle \psi^* | \hat{A} | \psi^* \rangle^* = (\langle \psi | \hat{A} | \psi \rangle)^*$$

故 $\bar{A} = \bar{A}^*$，$\bar{A}$ 为实数。

$$\langle \psi | \hat{A}^2 | \psi \rangle = \langle \psi | \hat{A}^\dagger \hat{A} | \psi \rangle = \langle \hat{A}\psi | \hat{A}\psi \rangle = \langle \phi | \phi \rangle \geq 0, \quad \overline{A^2} \geq 0$$

## 厄米算符本征值的实数性

$$\hat{F}|k\rangle = \lambda_k |k\rangle$$

则 $\langle k | \hat{F} | k \rangle = \bar{F} = \langle k | \lambda_k | k \rangle = \lambda_k \langle k | k \rangle = \lambda_k$，故 $\lambda_k = \bar{F}$ 为实数。

## 厄米算符本征态的正交性与完备性、封闭性

### ① 厄米算符属于不同本征值的本征态必然正交

（对不同 $|k\rangle$ 可能有不同的 $\lambda_k$）

$$\hat{F}|k\rangle = \lambda_k |k\rangle, \quad \hat{F}|k'\rangle = \lambda_{k'} |k'\rangle$$

$$\langle k' | \hat{F} | k \rangle = \lambda_k \langle k' | k \rangle, \quad \langle k' | \hat{F} | k \rangle = \langle k' | \hat{F}^\dagger | k \rangle = \langle \hat{F}k' | k \rangle = \lambda_{k'} \langle k' | k \rangle$$

又 $\lambda_k$ 为实数，故 $\lambda_k = \lambda_k^*$，$\lambda_k \langle k' | k \rangle = \lambda_{k'} \langle k' | k \rangle$，而 $\lambda_k \neq \lambda_{k'}$，故 $\langle k' | k \rangle = 0$，即 $|k'\rangle$ 与 $|k\rangle$ 正交。

### ② 本征态的完备性

$\hat{P}_k = |k\rangle\langle k|$ 为投影算符，$\hat{P}_k^2 = \hat{P}_k$。

若对 $\forall |\psi\rangle$，有 $\hat{P}|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = |\psi\rangle$，则称基矢 $|k\rangle$ 具有**完备性**。（任意 $|\psi\rangle$ 可按 $|k\rangle$ 展开）

记 $c_k = \langle k|\psi\rangle$，则 $|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = \sum_k c_k |k\rangle$，$c_k$ 为用 $|k\rangle$ 将 $|\psi\rangle$ 做展开时的展开系数。

**定理**：哈密顿算符 $\hat{H}$ 为厄米算符，满足本征方程 $\hat{H}|k\rangle = E_k |k\rangle$，对体系的任一归一化态 $|\psi\rangle$，若 $\bar{H} = \langle \psi | \hat{H} | \psi \rangle$ 有下界（总大于某常数）但无上界，则 $\hat{H}$ 的本征态 $|k\rangle$ 的集合构成体系的一个完备集，即体系的任一量子态 $|\psi\rangle$ 可用 $|k\rangle$ 来展开。

### ③ 本征态的封闭性

$\hat{I}$ 为单位算符。$\forall \psi$，$\hat{I}|\psi\rangle = |\psi\rangle$。

若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = \hat{I}$，称为本征态或基矢 $|k\rangle$ 的**封闭性**；$\sum_k \hat{P}_k = \sum_k |k\rangle\langle k| = \hat{I}$，称为投影算符 $\hat{P}_k$ 的封闭性。

> **完备性 & 封闭性**：强调重点不同，完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开，封闭性指数学上封闭性方程 $\sum_k |k\rangle\langle k| = \hat{I}$ 成立，两者相互依存。

**例**：设体系的能量本征方程为 $\hat{H}|k\rangle = E_k |k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k |k\rangle\langle k|$（本征态具有完备性、封闭性）。

$$\hat{H}|k\rangle\langle k| = E_k |k\rangle\langle k|$$

则 $\sum_k \hat{H}|k\rangle\langle k| = \hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k |k\rangle\langle k|$，从而有 $\hat{H}\hat{I} = \hat{H} = \sum_k E_k |k\rangle\langle k|$。

---

# 守恒量与能级简并度

## 力学量平均值的时间依赖特性

$$\bar{A}(t) = \langle \psi(t) | \hat{A} | \psi(t) \rangle$$

薛定谔方程：$i\hbar \frac{\partial}{\partial t}|\psi(t)\rangle = \hat{H}|\psi(t)\rangle$。在左矢空间中：$-i\hbar \frac{\partial}{\partial t}\langle \psi | = \langle \psi | \hat{H}$（$\hat{H}^\dagger = \hat{H}$）。

$$\frac{d\bar{A}}{dt} = \frac{\partial}{\partial t}\left( \langle \psi | \hat{A} | \psi \rangle \right) = \frac{1}{i\hbar}\langle \psi | \hat{A}\hat{H} | \psi \rangle + \langle \psi | \frac{\partial \hat{A}}{\partial t} | \psi \rangle - \frac{1}{i\hbar}\langle \psi | \hat{H}\hat{A} | \psi \rangle$$

$$\frac{d\bar{A}}{dt} = \frac{1}{i\hbar}\langle \psi | [\hat{A}, \hat{H}] | \psi \rangle + \left\langle \psi \left| \frac{\partial \hat{A}}{\partial t} \right| \psi \right\rangle$$

若 $\frac{\partial \hat{A}}{\partial t} = 0$（$\hat{A}$ 不显含 $t$）且 $[\hat{A}, \hat{H}] = 0$，则 $\frac{d\bar{A}}{dt} = 0$，$\bar{A}$ 与时间无关，$A$ 在任何态 $\psi(t)$ 下的平均值 $\bar{A}$ 都不随时间改变。

## 守恒量

$A$ 在任何态 $\psi(t)$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $A$ 对应的力学量为体系的一个**守恒量**。

$$\frac{\partial \hat{A}}{\partial t} = 0 \text{ 且 } [\hat{A}, \hat{H}] = 0 \Rightarrow A \text{ 为守恒量}$$

**定理**：若 $[\hat{F}, \hat{H}] = 0$，$[\hat{G}, \hat{H}] = 0$，但 $[\hat{F}, \hat{G}] \neq 0$，则体系的能级是简并的。（$F$、$G$ 为守恒量）

**证明**：$\hat{F}$、$\hat{H}$ 有共同本征函数 $\psi$：$\hat{F}\psi = F\psi$，$\hat{H}\psi = E\psi$。又 $[\hat{G}, \hat{H}] = 0$，则 $\hat{H}(\hat{G}\psi) = \hat{G}\hat{H}\psi = E(\hat{G}\psi)$，即 $\hat{G}\psi$ 也是 $\hat{H}$ 属于 $E$ 的本征态。又 $\hat{F}(\hat{G}\psi) = \hat{G}\hat{F}\psi \neq F(\hat{G}\psi)$，则 $\hat{G}\psi$ 不是 $\hat{F}$ 的本征态，$\hat{G}\psi$ 和 $\psi$ 不是同一个态，即 $E$ 对应至少两个态，能级简并。

---

# 表象变换与矩阵力学

设 $\hat{F} = (\hat{A}_1, \hat{A}_2, \ldots, \hat{A}_n)$ 是一组力学量完全集，$\psi_k \equiv |k\rangle$ 是其共同本征态，其中 $k$ 表征所有量子数。

$|k\rangle$ 是正交归一的，满足 $\langle k | m \rangle = \delta_{km} = \begin{cases} 1, & k = m \\ 0, & k \neq m \end{cases}$，$|k\rangle$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。

$\{|k\rangle\}$ 构成一个表象，可称为 $F$ 表象。$F$ 构成无穷维的希尔伯特空间，量子态 $\psi$ 是希尔伯特空间中的一个矢量。

$$|\psi\rangle = \sum_k a_k |k\rangle$$

则 $a_k = \langle k | \psi \rangle$ 为内积，也可视为"投影"。

## 表象间的转化

$F$ 表象中，$|k\rangle = \psi_k$，$\psi = \sum_k a_k |k\rangle$，$\psi$ 在 $F$ 表象中可用系数列向量表示为 $a = \begin{pmatrix} a_1 \\ a_2 \\ \vdots \end{pmatrix}$。

另一 $F'$ 表象中，$|\beta\rangle = \psi_\beta$ 为基矢，$\psi = \sum_\beta a_\beta |\beta\rangle$，在 $F'$ 表象中可表示为 $a' = \begin{pmatrix} a_1' \\ a_2' \\ \vdots \end{pmatrix}$。

$a'$ 与 $a$ 的转化实际上是基矢之间的转化。

$$\psi = \sum_k a_k |k\rangle = \sum_\beta b_\beta |\beta\rangle$$

$|k\rangle = \sum_\beta \langle \beta | k \rangle \cdot |\beta\rangle$（$|k\rangle$ 按 $|\beta\rangle$ 展开），从而统一基矢为 $|\beta\rangle$。

记 $S_{\beta k} = \langle \beta | k \rangle$，$S = (S_{\beta k})$，则 $a_\beta' = \sum_k a_k \cdot \langle \beta | k \rangle$，$a' = S a$。

$$S^\dagger S = S S^\dagger = I$$

> **注**：$a$、$a'$ 均为系数列向量，与本征态形式相似但意义完全不同。$|k\rangle$ 在希尔伯特空间中可表示为一个列向量，$|\psi\rangle$ 按 $|k\rangle$ 展开所得系数列为 $a$。

从矢量的角度考虑，$|\psi\rangle = (e_1, e_2, \ldots, e_k, \ldots) \begin{pmatrix} a_1 \\ a_2 \\ \vdots \end{pmatrix}$，列向量 $e_k'$ 的线性组合系数列。

要"消去" $(e_1', e_2', \ldots, e_k', \ldots)$，则 $(e_1, e_2, \ldots, e_k, \ldots) = (e_1', e_2', \ldots, e_k', \ldots) S$。

$$\langle k' | k \rangle = \delta_{k'k}, \quad \langle k | k \rangle = 1$$

$$|k\rangle = \sum_\beta S_{\beta k} |\beta\rangle$$

$$\langle k' | k \rangle = \left( \sum_\beta S_{\beta k'}^* \langle \beta | \right) \left( \sum_\gamma S_{\gamma k} |\gamma\rangle \right) = \sum_\beta S_{\beta k'}^* S_{\beta k} = \delta_{k'k}$$

即 $S^\dagger S = I$，**$S$ 为幺正矩阵**。

---

# 中心力场

$$\hat{H} = -\frac{\hbar^2}{2\mu}\nabla^2 + V(\vec{r}), \quad V(\vec{r}) = V(r)$$

称为**中心力场**。

$\nabla^2$ 在坐标表象下为 $\nabla^2 = \frac{1}{r^2}\frac{\partial}{\partial r}\left( r^2 \frac{\partial}{\partial r} \right) + \frac{1}{r^2 \sin\theta}\frac{\partial}{\partial\theta}\left( \sin\theta \frac{\partial}{\partial\theta} \right) + \frac{1}{r^2 \sin^2\theta}\frac{\partial^2}{\partial\varphi^2}$。

又 $\hat{L}^2 = -\hbar^2 \left[ \frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left( \sin\theta \frac{\partial}{\partial\theta} \right) + \frac{1}{\sin^2\theta}\frac{\partial^2}{\partial\varphi^2} \right]$，于是：

$$-\frac{\hbar^2}{2\mu}\frac{1}{r^2}\frac{\partial}{\partial r}\left( r^2 \frac{\partial \psi}{\partial r} \right) + \frac{\hat{L}^2}{2\mu r^2}\psi + V(r)\psi = E\psi$$

采用分离变量法，令 $\psi(r, \theta, \varphi) = R(r)Y(\theta, \varphi)$：

$$-\frac{\hbar^2}{2\mu}\frac{1}{r^2}\frac{d}{dr}\left( r^2 \frac{dR}{dr} \right) Y + \frac{1}{2\mu r^2} R \hat{L}^2 Y + (V(r) - E) R Y = 0$$

$$\frac{1}{R}\frac{d}{dr}\left( r^2 \frac{dR}{dr} \right) + \frac{2\mu r^2}{\hbar^2}(E - V(r)) = -\frac{1}{\hbar^2 Y}\hat{L}^2 Y = \lambda$$

**径向方程**：

$$\frac{1}{r^2}\frac{d}{dr}\left( r^2 \frac{dR}{dr} \right) + \left[ \frac{2\mu}{\hbar^2}(E - V(r)) - \frac{\lambda}{r^2} \right] R(r) = 0$$

**角向方程**：

$$\hat{L}^2 Y(\theta, \varphi) = \lambda \hbar^2 Y(\theta, \varphi)$$

### ① 角向方程

$Y(\theta, \varphi) = \Theta(\theta)\Phi(\varphi)$：

$$\frac{1}{\sin\theta}\frac{d}{d\theta}\left( \sin\theta \frac{d\Theta}{d\theta} \right) \Phi + \frac{1}{\sin^2\theta}\Theta \frac{d^2\Phi}{d\varphi^2} = -\lambda \Theta \Phi$$

$$\Rightarrow \frac{\sin\theta}{\Theta}\frac{d}{d\theta}\left( \sin\theta \frac{d\Theta}{d\theta} \right) + \lambda \sin^2\theta = -\frac{1}{\Phi}\frac{d^2\Phi}{d\varphi^2} = m^2$$

\$\$\frac{1}{\sin\theta}\frac{d}{d\theta}\left( \sin\theta \frac{d\Theta}{d\theta} \right) + \left( \lambda - \frac{m^2}{\