# 常见对易恒等式

$$[A,B] = -[B,A]$$

$$[A,B+C] = [A,B] + [A,C]$$

$$[A,BC] = [A,B]C + B[A,C]$$

$$[AB,C] = A[B,C] + [A,C]B$$

$$[A,[B,C]] + [B,[C,A]] + [C,[A,B]] = 0 \quad \text{（Jacobi 恒等式）}$$

$$[A,B+C] + [B,A+C] + [C,A+B] = 0$$

---

## 利用对易关系求解平均值问题

真＝[mt<(m|G|(m>-<|m|G|(m>]．六及＝瓦＝0

**例1.** 求 $\hat{L}_x$ 和 $\hat{L}_y$ 在 $|lm\rangle$ 下的平均值。

已知 $\hat{L}_z|lm\rangle = m\hbar|lm\rangle$，$[\hat{L}_y, \hat{L}_z] = i\hbar \hat{L}_x$，$[\hat{L}_z, \hat{L}_x] = i\hbar \hat{L}_y$，从而可用含 $\hat{L}_z$ 的表达式表出 $\hat{L}_x$、$\hat{L}_y$。

$$\langle \hat{L}_x \rangle = \langle lm|\hat{L}_x|lm\rangle = \frac{1}{i\hbar}\langle lm|[\hat{L}_y, \hat{L}_z]|lm\rangle = \frac{1}{i\hbar}\left[\langle lm|\hat{L}_y\hat{L}_z|lm\rangle - \langle lm|\hat{L}_z\hat{L}_y|lm\rangle\right]$$

由于 $\hat{L}_z|lm\rangle = m\hbar|lm\rangle$，$m$ 为实数，则 $\langle lm|\hat{L}_z = m\hbar\langle lm|$，代入得：

$$\langle \hat{L}_x \rangle = \frac{1}{i\hbar}\left[m\hbar\langle lm|\hat{L}_y|lm\rangle - m\hbar\langle lm|\hat{L}_y|lm\rangle\right] = 0$$

同理 $\langle \hat{L}_y \rangle = 0$。

**例2.** $|lm\rangle$ 为 $(\hat{L}^2, \hat{L}_z)$ 的共同本征态，求 $\overline{\hat{L}_x^2}$、$\overline{\hat{L}_y^2}$。

$$\overline{\hat{L}_x^2} = \langle lm|\hat{L}_x^2|lm\rangle = \langle lm|(\hat{L}^2 - \hat{L}_z^2)|lm\rangle = l(l+1)\hbar^2 - m^2\hbar^2$$

利用 $[\hat{L}_x, \hat{L}_y] = i\hbar\hat{L}_z$，可得 $\hat{L}_x\hat{L}_y - \hat{L}_y\hat{L}_x = i\hbar\hat{L}_z$，从而：

$$\overline{\hat{L}_x^2} = \overline{\hat{L}_y^2} = \frac{1}{2}\left[l(l+1) - m^2\right]\hbar^2$$

**方法总结：** 将本征态对应的算符尽量转化到最左/右边，直接作用到态矢上。

---

## 不确定度关系的严格证明

任意给定力学量 $A$ 和 $B$，对应的厄米算符为 $\hat{A}$ 和 $\hat{B}$，分别具有不确定度 $\Delta A$ 和 $\Delta B$，则有以下关系：

$$\Delta A \cdot \Delta B \geq \frac{1}{2}\left|\langle[\hat{A},\hat{B}]\rangle\right|$$

其中 $\langle[\hat{A},\hat{B}]\rangle = \langle\psi|[\hat{A},\hat{B}]|\psi\rangle$ 对 $\forall|\psi\rangle$ 成立，$\Delta A = \hat{A} - \bar{A}$，$\Delta B = \hat{B} - \bar{B}$。

$$[\hat{A},\hat{B}] = [\Delta A + \bar{A}, \Delta B + \bar{B}] = (\Delta A + \bar{A})(\Delta B + \bar{B}) - (\Delta B + \bar{B})(\Delta A + \bar{A}) = [\Delta A, \Delta B]$$

$$\Delta A = \sqrt{\overline{(\hat{A} - \bar{A})^2}}, \quad \Delta B = \sqrt{\overline{(\hat{B} - \bar{B})^2}}$$

要证即 $\overline{(\hat{A}-\bar{A})^2} \cdot \overline{(\hat{B}-\bar{B})^2} \geq \frac{1}{4}\left|\overline{[\hat{A}-\bar{A}, \hat{B}-\bar{B}]}\right|^2$。

令 $\hat{X} = \hat{A} - \bar{A}$，$\hat{Y} = \hat{B} - \bar{B}$，要证变为 $\overline{X^2} \cdot \overline{Y^2} \geq \frac{1}{4}\left|\overline{[X,Y]}\right|^2$。联想 $b^2 \geq 4ac$。

考虑 $|\phi\rangle = \xi\hat{X}|\psi\rangle + i\eta\hat{Y}|\psi\rangle$，$\langle\phi|\phi\rangle \geq 0$：

$$\langle\phi|\phi\rangle = (\xi\langle\psi|\hat{X}^\dagger - i\eta\langle\psi|\hat{Y}^\dagger)(\xi\hat{X}|\psi\rangle + i\eta\hat{Y}|\psi\rangle)$$

$\hat{X}$、$\hat{Y}$ 为厄米算符：

$$= (\xi\langle\psi|\hat{X} - i\eta\langle\psi|\hat{Y})(\xi\hat{X}|\psi\rangle + i\eta\hat{Y}|\psi\rangle)$$

$$= \xi^2\langle\psi|\hat{X}^2|\psi\rangle + \eta^2\langle\psi|\hat{Y}^2|\psi\rangle + i\xi\eta\left(\langle\psi|\hat{X}\hat{Y}|\psi\rangle - \langle\psi|\hat{Y}\hat{X}|\psi\rangle\right)$$

$$= \xi^2\overline{X^2} + \eta^2\overline{Y^2} + i\xi\eta\overline{[X,Y]}$$

由 $\langle\phi|\phi\rangle \geq 0$，取 $\xi, \eta$ 使判别式 $\leq 0$，即 $\overline{X^2} \cdot \overline{Y^2} \geq \frac{1}{4}\left|\overline{[X,Y]}\right|^2$。

$$\Rightarrow \Delta A \cdot \Delta B \geq \frac{1}{2}\left|\langle[\hat{A},\hat{B}]\rangle\right|$$

**结论：** 对任意力学量 $A$、$B$，任意量子态 $|\psi\rangle$，若 $A$ 与 $B$ 不对易即 $[\hat{A},\hat{B}] \neq 0$，则 $\Delta A$ 和 $\Delta B$ 不能同时为零，也即 **$A$ 与 $B$ 不能同时测定**。

---

## 共同本征函数

设 $\hat{A}\psi_A = A\psi_A$，$\hat{B}\psi_B = B\psi_B$。若 $[\hat{A},\hat{B}] \neq 0$，则 $\psi_A$ 不是 $\hat{B}$ 的本征函数，$\psi_B$ 不是 $\hat{A}$ 的本征函数。

若 $[\hat{A},\hat{B}] = 0$，则可能存在 $\psi$，使 $\hat{A}\psi = A\psi$，$\hat{B}\psi = B\psi$。此时称 $\psi$ 为 $A$ 和 $B$ 的**共同本征函数**。

**定理：** 设 $\hat{A}|k\rangle = a_k|k\rangle$，另有 $\hat{B}$，若 $[\hat{A},\hat{B}] = 0$，且 $a_k$ 不简并（即 $a_k$ 只对应一个本征态 $|k\rangle$），则 $|k\rangle$ 也是 $\hat{B}$ 的本征态，即 $A$ 和 $B$ 拥有共同本征态。

**证明：** $[\hat{A},\hat{B}] = 0 \Rightarrow \hat{A}\hat{B} = \hat{B}\hat{A}$。$\hat{B}\hat{A}|k\rangle = \hat{B} \cdot a_k|k\rangle = a_k\hat{B}|k\rangle$。则 $\hat{A}(\hat{B}|k\rangle) = a_k(\hat{B}|k\rangle)$，即 $\hat{B}|k\rangle$ 也是 $A$ 属于本征值 $a_k$ 的本征态。故 $\hat{B}|k\rangle$ 与 $|k\rangle$ 是同一个态，即 $\hat{B}|k\rangle = b_k|k\rangle$。$\Rightarrow A$、$B$ 拥有共同本征态 $|k\rangle$。

**例：** $\psi_p(\vec{r}) = \frac{1}{(2\pi\hbar)^{3/2}}e^{i\vec{p}\cdot\vec{r}/\hbar}$ 为 $\hat{p}_x, \hat{p}_y, \hat{p}_z$ 的共同本征函数，本征值为 $p_x, p_y, p_z$。$\hat{p}\psi_p(\vec{r}) = \vec{p}\psi_p(\vec{r})$。

---

## 厄米算符本征值与本征态的特性

### 转置算符、共轭算符与厄米算符

$$\int \psi_A^* \hat{A}\phi \, d\tau = \int \phi \hat{A}^T\psi_A^* \, d\tau$$

**转置算符：** 对 $\forall\psi$ 和 $\phi$，若 $\langle\psi|\hat{A}|\phi\rangle = \langle\phi|\hat{A}^T|\psi\rangle$，则称 $\hat{A}$ 和 $\hat{A}^T$ 互为彼此的转置算符。

**共轭算符：** 对算符 $\hat{A}$ 的每一项取复共轭，得到 $\hat{A}^*$ 为 $\hat{A}$ 的转置算符。

**厄米算符：** $\hat{A} = \hat{A}^\dagger = \hat{A}^{*T}$，则称 $\hat{A}$ 为厄米算符。

### 厄米算符平均值的实数性

**定理：** 厄米算符 $\hat{A}$ 在任意量子态下的平均值 $\bar{A}$ 为实数，$\bar{A^2} \geq 0$。

$$\langle\psi|\hat{A}|\psi\rangle = \langle\psi|\hat{A}^\dagger|\psi\rangle = \langle\psi|\hat{A}^*|\psi\rangle = \langle\psi^*|\hat{A}|\psi^*\rangle^* = (\langle\psi|\hat{A}|\psi\rangle)^*$$

故 $\bar{A} = \bar{A}^*$，$\bar{A}$ 为实数。

$$\langle\psi|\hat{A}^2|\psi\rangle = \langle\psi|\hat{A}^\dagger\hat{A}|\psi\rangle = \langle\hat{A}\psi|\hat{A}\psi\rangle = \langle\phi|\phi\rangle \geq 0, \quad \bar{A^2} \geq 0$$

### 厄米算符本征值的实数性

$$\hat{F}|k\rangle = \lambda_k|k\rangle, \quad \langle k|\hat{F}|k\rangle = \bar{F} = \langle k|\lambda_k|k\rangle = \lambda_k\langle k|k\rangle = \lambda_k$$

故 $\lambda_k = \bar{F}$ 为实数。

### 厄米算符本征态的正交性与完备性、封闭性

从而有 $a_{j+2} = \frac{2(j-n)}{(j+1)(j+2)} a_j$，多项式 $H(s)$ 只能含奇数项或偶数项，系数由高次项推至低次项。

**① 厄米算符属于不同本征值的本征态必然正交**（对不同 $|k\rangle$ 可能有不同的 $\lambda_k$）：

$$\hat{F}|k\rangle = \lambda_k|k\rangle, \quad \hat{F}|k'\rangle = \lambda_{k'}|k'\rangle$$

$$\langle k'|\hat{F}|k\rangle = \lambda_k\langle k'|k\rangle, \quad \langle k'|\hat{F}|k\rangle = \langle k'|\hat{F}^\dagger|k\rangle = \langle \hat{F}k'|k\rangle = \lambda_{k'}\langle k'|k\rangle$$

又 $\lambda_k$ 为实数，故 $\lambda_k = \lambda_k^*$，$\langle k'|\hat{F}|k\rangle = \lambda_k\langle k'|k\rangle = \lambda_{k'}\langle k'|k\rangle$，而 $\lambda_k \neq \lambda_{k'}$，故 $\langle k'|k\rangle = 0$，即 $|k'\rangle$ 与 $|k\rangle$ 正交。

**② 本征态的完备性**

$\hat{P}_k = |k\rangle\langle k|$ 为投影算符，$\hat{P}_k^2 = \hat{P}_k$。

若对 $\forall|\psi\rangle$，有 $\hat{P}|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = |\psi\rangle$，则称基矢 $|k\rangle$ 具有完备性（任意 $|\psi\rangle$ 可按 $|k\rangle$ 展开）。

记 $c_k = \langle k|\psi\rangle$，则 $|\psi\rangle = \sum_k |k\rangle\langle k|\psi\rangle = \sum_k c_k|k\rangle$，$c_k$ 为用 $|k\rangle$ 将 $|\psi\rangle$ 做展开时的展开系数。

**定理：** 哈密顿算符 $\hat{H}$ 为厄米算符，满足本征方程 $\hat{H}|k\rangle = E_k|k\rangle$，对体系的任一归一化态 $|\psi\rangle$，若 $\bar{H} = \langle\psi|\hat{H}|\psi\rangle$ 有下界（总大于某常数）但无上界，则 $\hat{H}$ 的本征态 $|k\rangle$ 的集合构成体系的一个完备集，即体系的任一量子态 $|\psi\rangle$ 可用 $|k\rangle$ 来展开。

**③ 本征态的封闭性**

$\hat{I}$ 为单位算符。$\forall\psi$，$\hat{I}|\psi\rangle = |\psi\rangle$。

若本征态或基矢 $|k\rangle$ 满足 $\sum_k |k\rangle\langle k| = \hat{I}$，称为本征态或基矢 $|k\rangle$ 的**封闭性**；$\sum_k \hat{P}_k = \sum_k |k\rangle\langle k| = \hat{I}$，称为投影算符 $\hat{P}_k$ 的封闭性。

**完备性 & 封闭性：** 强调重点不同，完备性指任意 $|\psi\rangle$ 可按 $\{|k\rangle\}$ 展开，封闭性指数学上封闭性方程 $\sum_k |k\rangle\langle k| = \hat{I}$ 成立，两者相互依存。

**例：** 设体系的能量本征方程为 $\hat{H}|k\rangle = E_k|k\rangle$，证明哈密顿算符可表示为 $\hat{H} = \sum_k E_k|k\rangle\langle k|$（本征态具有完备性、封闭性）。

$$\hat{H}|k\rangle\langle k| = E_k|k\rangle\langle k|, \quad \sum_k \hat{H}|k\rangle\langle k| = \hat{H}\sum_k |k\rangle\langle k| = \sum_k E_k|k\rangle\langle k|$$

从而有 $\hat{H}\hat{I} = \hat{H} = \sum_k E_k|k\rangle\langle k|$。

---

## 守恒量与能级简并度

### 力学量平均值的时间依赖特性

$$\bar{A}(t) = \langle\psi(t)|\hat{A}(t)|\psi(t)\rangle$$

薛定谔方程：$i\hbar\frac{\partial}{\partial t}|\psi(t)\rangle = \hat{H}|\psi\rangle$。在左矢空间中：$-i\hbar\frac{\partial}{\partial t}\langle\psi| = \langle\psi|\hat{H}$（$\hat{H}^\dagger = \hat{H}$）。

$$\frac{d\bar{A}}{dt} = \frac{\partial}{\partial t}\left(\langle\psi|\hat{A}|\psi\rangle\right) = \langle\frac{\partial\psi}{\partial t}|\hat{A}|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle + \langle\psi|\hat{A}|\frac{\partial\psi}{\partial t}\rangle$$

$$= -\frac{1}{i\hbar}\langle\psi|\hat{H}\hat{A}|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle + \frac{1}{i\hbar}\langle\psi|\hat{A}\hat{H}|\psi\rangle$$

$$\frac{d\bar{A}}{dt} = \frac{1}{i\hbar}\langle\psi|[\hat{A},\hat{H}]|\psi\rangle + \langle\psi|\frac{\partial\hat{A}}{\partial t}|\psi\rangle$$

若 $\frac{\partial\hat{A}}{\partial t} = 0$（$\hat{A}$ 不显含 $t$）且 $[\hat{A},\hat{H}] = 0$，则 $\frac{d\bar{A}}{dt} = 0$，$\bar{A}$ 与时间无关，$A$ 在任何态 $\psi(t)$ 下的平均值 $\bar{A}$ 都不随时间改变。

### 守恒量

$A$ 在任何态 $\psi(t)$ 下的平均值 $\bar{A}$ 都不随 $t$ 改变，则称此时 $A$ 对应的力学量为体系的一个**守恒量**。

$$\frac{\partial\hat{A}}{\partial t} = 0 \text{ 且 } [\hat{A},\hat{H}] = 0 \Rightarrow A \text{ 为守恒量}$$

**定理：** 若 $[\hat{F},\hat{H}] = 0$，$[\hat{G},\hat{H}] = 0$，但 $[\hat{F},\hat{G}] \neq 0$，则体系的能级是简并的（$F$、$G$ 为守恒量）。

**证明：** $\hat{F}$、$\hat{H}$ 有共同本征函数 $\psi$：$\hat{F}\psi = F\psi$，$\hat{H}\psi = E\psi$。由 $[\hat{G},\hat{H}] = 0$，则 $\hat{H}(\hat{G}\psi) = \hat{G}\hat{H}\psi = E(\hat{G}\psi)$，即 $\hat{G}\psi$ 也是 $\hat{H}$ 属于 $E$ 的本征态。又 $\hat{F}(\hat{G}\psi) = \hat{G}\hat{F}\psi \neq F(\hat{G}\psi)$（因 $[\hat{F},\hat{G}] \neq 0$），则 $\hat{G}\psi$ 不是 $\hat{F}$ 的本征态，$\hat{G}\psi$ 和 $\psi$ 不是一个态，即 $E$ 对应至少两个态，能级简并。

---

## 表象变换与矩阵力学

设 $\hat{F} = (\hat{A}_1, \hat{A}_2, \ldots, \hat{A}_n)$ 是一组力学量完全集，$\psi_k \equiv |k\rangle$ 是其共同本征态，其中 $k$ 表征所有量子数。

$|k\rangle$ 是正交归一的，满足 $\langle k|m\rangle = \delta_{km} = \begin{cases} 1, & k = m \\ 0, & k \neq m \end{cases}$，$|k\rangle$ 是完备的，即体系中任一量子态可按 $|k\rangle$ 展开。

$\{|k\rangle\}$ 构成一个表象，可称为 $F$ 表象。$F$ 构成无穷维的希尔伯特空间，量子态 $\psi$ 是希尔伯特空间中的一个矢量。$|\psi\rangle = \sum_k a_k|k\rangle$，则 $a_k = \langle k|\psi\rangle$ 为内积，也可视为"投影"。

### 表象间的转化

$F$ 表象中，$|k\rangle = \psi_k$，$\psi = \sum_k a_k|k\rangle$，$\psi$ 在 $F$ 表象中可用系数列向量表示为 $a = (a_1, a_2, \ldots)^T$。

另一 $F'$ 表象中，$|\beta\rangle = \psi_\beta$ 为基矢，$\psi = \sum_\beta a_\beta|\beta\rangle$，在 $F'$ 表象中可表示为 $a' = (a_\beta)$。

$a'$ 与 $a$ 的转化实际上是基矢之间的转化。

$$\psi = \sum_k a_k|k\rangle = \sum_\beta b_\beta|\beta\rangle, \quad |k\rangle = \sum_\beta \langle\beta|k\rangle \cdot |\beta\rangle \quad (|k\rangle \text{ 按 } |\beta\rangle \text{ 展开})$$

从而统一基矢为 $|\beta\rangle$。

记 $S_{\beta k} = \langle\beta|k\rangle$，$S = (S_{\beta k})$，则 $a_\beta = \sum_k a_k \cdot \langle\beta|k\rangle$，$a' = Sa$。

由 $\langle k'|k\rangle = \delta_{k'k}$，$\langle k|k\rangle = 1$，$|k\rangle = \sum_\beta S_{\beta k}|\beta\rangle$：

$$\langle k'|k\rangle = \left(\sum_\beta S_{\beta k'}^*\langle\beta|\right)\left(\sum_\beta S_{\beta k}|\beta\rangle\right) = \sum_\beta S_{\beta k'}^* S_{\beta k} = \delta_{k'k}$$

即 $S^\dagger S = I$，**$S$ 为幺正矩阵**。

**注：** $a$、$a'$ 均为系数列向量，与本征态形式相似但意义完全不同。$|k\rangle$ 在希尔伯特空间中可表示为一个列向量，$|\psi\rangle$ 按 $|k\rangle$ 展开所得系数列为 $a$。

---

## 中心力场

$$\hat{H} = -\frac{\hbar^2}{2\mu}\nabla^2 + V(\vec{r}), \quad V(\vec{r}) = V(r)$$

称为**中心力场**。

$\nabla^2$ 在坐标表象下为 $\nabla^2 = \frac{1}{r^2}\frac{\partial}{\partial r}\left(r^2\frac{\partial}{\partial r}\right) + \frac{1}{r^2\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial}{\partial\theta}\right) + \frac{1}{r^2\sin^2\theta}\frac{\partial^2}{\partial\varphi^2}$。

又 $\hat{L}^2 = -\hbar^2\left[\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2}{\partial\varphi^2}\right]$，于是：

$$-\frac{\hbar^2}{2\mu}\frac{1}{r^2}\frac{\partial}{\partial r}\left(r^2\frac{\partial\psi}{\partial r}\right) + \frac{\hat{L}^2}{2\mu r^2}\psi + [V(r) - E]\psi = 0$$

采用分离变量法，令 $\psi(r,\theta,\varphi) = R(r)Y(\theta,\varphi)$：

$$-\frac{\hbar^2}{2\mu}\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right)Y + \frac{\hat{L}^2Y}{2\mu r^2}R + [V(r) - E]R \cdot Y = 0$$

$$\frac{1}{R}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \frac{2\mu r^2}{\hbar^2}[V(r) - E] = -\frac{1}{Y}\frac{\hat{L}^2Y}{\hbar^2} = \lambda$$

**径向方程：**

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}(E - V(r)) - \frac{\lambda}{r^2}\right]R(r) = 0$$

**角向方程：**

$$\frac{1}{\sin\theta}\frac{\partial}{\partial\theta}\left(\sin\theta\frac{\partial Y}{\partial\theta}\right) + \frac{1}{\sin^2\theta}\frac{\partial^2Y}{\partial\varphi^2} = -\lambda Y(\theta,\varphi)$$

即 $\hat{L}^2Y(\theta,\varphi) = \lambda\hbar^2Y(\theta,\varphi)$。

### ① 角向方程

$Y(\theta,\varphi) = \Theta(\theta)\Phi(\varphi)$：

$$\frac{\sin\theta}{\Theta}\frac{d}{d\theta}\left(\sin\theta\frac{d\Theta}{d\theta}\right) + \lambda\sin^2\theta = -\frac{1}{\Phi}\frac{d^2\Phi}{d\varphi^2} = m^2$$

$$\frac{1}{\sin\theta}\frac{d}{d\theta}\left(\sin\theta\frac{d\Theta}{d\theta}\right) + \left(\lambda - \frac{m^2}{\sin^2\theta}\right)\Theta(\theta) = 0 \quad \text{（勒让德方程）}$$

$$\frac{d^2\Phi}{d\varphi^2} + m^2\Phi(\varphi) = 0 \Rightarrow \Phi_m(\varphi) = \frac{1}{\sqrt{2\pi}}e^{im\varphi}$$

对于勒让德方程，为使 $\Theta(\theta)$ 在区间 $[0,\pi]$ 有限，$\lambda$ 只能取 $l(l+1)$，$l = 0,1,2,\ldots$（$l$ 为轨道量子数）：

$$\Theta(\theta) = \Theta_{lm}(\theta) = P_l^m(\cos\theta) = B_{lm}(1-\cos^2\theta)^{|m|/2}\frac{d^{|m|}}{d(\cos\theta)^{|m|}}P_l(\cos\theta)$$

$|m| \leq l$ 时才有 $\Theta(\theta) \neq 0$，即 $m = 0, \pm 1, \ldots, \pm l$。

$$\int_0^\pi \Theta_{lm}^*(\theta)\Theta_{lm}(\theta)\sin\theta\,d\theta = \delta_{ll'}$$

球谐函数：

$$Y_{lm}(\theta,\varphi) = \Theta_{lm}(\theta)\Phi_m(\varphi) = N_{lm}(1-\cos^2\theta)^{|m|/2}\frac{d^{|m|}}{d(\cos\theta)^{|m|}}P_l(\cos\theta)e^{im\varphi}$$

$$N_{lm} = \sqrt{\frac{2l+1}{4\pi}\frac{(l-|m|)!}{(l+|m|)!}}$$

球谐函数满足正交关系：

$$\int_0^{2\pi}\int_0^\pi Y_{lm}^*(\theta,\varphi)Y_{l'm'}(\theta,\varphi)\sin\theta\,d\theta\,d\varphi = \delta_{ll'}\delta_{mm'}$$

$$\hat{L}^2Y_{lm} = l(l+1)\hbar^2Y_{lm}, \quad \hat{L}_zY_{lm} = m\hbar Y_{lm}$$

$\Rightarrow Y_{lm}$ 是 $\hat{L}^2$、$\hat{L}_z$ 的共同本征态。

---

## 氢原子

径向方程：

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}\left(E - V(r)\right) - \frac{l(l+1)}{r^2}\right]R = 0$$

$$V(r) = -\frac{e^2}{4\pi\varepsilon_0 r} = -\frac{ke^2}{r}$$

则方程为：

$$\frac{1}{r^2}\frac{d}{dr}\left(r^2\frac{dR}{dr}\right) + \left[\frac{2\mu}{\hbar^2}\left(E + \frac{ke^2}{r}\right) - \frac{l(l+1)}{r^2}\right]R(r) = 0$$

引入约化径向波函数 $u(r) = rR_l(r)$，则 $u(r)$ 满足：

$$\frac{d^2u}{dr^2} + \left[\frac{2\mu}{\hbar^2}\left(E + \frac{ke^2}{r}\right) - \frac{l(l+1)}{r^2}\right]u(r) = 0$$

$V(r) < 0$，$R_l(r) \to 0$（$r \to \infty$）。$r \to \infty$ 时薛定谔方程约为 $\frac{d^2u}{dr^2} + \frac{2\mu E}{\hbar^2}u(r) = 0$，若 $E > 0$，$u(r)$ 呈振荡形式，不满足束缚态，则 $E < 0$。从能量角度分析，$E = V + K$，$K < |V|$，$E < 0$。

### 核与电子"双星模型"

$\mu$ 为约化质量，$\mu = \frac{m_e m_N}{m_e + m_N}$。定义无量纲变量 $\rho = \alpha r$，$\alpha = \frac{\sqrt{-2\mu E}}{\hbar}$，$\beta = \frac{\mu ke^2}{\hbar^2\alpha}$。

于是方程化为：

$$\frac{d^2u}{d\rho^2} + \left[-\frac{1}{4} + \frac{\beta}{\rho} - \frac{l(l+1)}{\rho^2}\right]u(\rho) = 0$$

$\rho \to \infty$ 时，方程近似为 $\frac{d^2u}{d\rho^2} - \frac{1}{4}u(\rho) = 0$，$u(\rho) \sim e^{-\rho/2}$（$\rho \to \infty$）。

$\rho \to 0$ 时，方程近似为 $\frac{d^2u}{d\rho^2} - \frac{l(l+1)}{\rho^2}u(\rho) = 0$，$u(\rho) \sim \rho^{l+1}$。

利用渐进解，设 $u(\rho) = \rho^{l+1}e^{-\rho/2}v(\rho)$。

$v(\rho)$ 满足方程：

$$\rho\frac{d^2v}{d\rho^2} + (2l+2-\rho)\frac{dv}{d\rho} + [\beta - (l+1)]v(\rho) = 0$$

为**合流超几何方程**。

$v(\rho)$ 有多项式解的条件是 $\beta - (l+1) = n_r$，$\beta = l + 1 + n_r$（$n_r = 0,1,\ldots$）。令 $n = l + 1 + n_r$，$n = 1,2,\ldots$：

$$E_n = -\frac{\mu k^2e^4}{2\hbar^2n^2}$$

$$\beta = \frac{\mu ke^2}{\hbar^2\alpha} = n, \quad E_n = -\frac{\mu k^2e^4}{2\hbar^2n^2} \text{ 仅与 } n \text{ 相关}$$

$l$ 的取值为 $0,1,\ldots,n-1$；$m$ 的取值为 $-l, -(l-1), \ldots, 0, 1, \ldots, l$。能量本征态由 $(n,l,m)$ 表征。

**氢原子轨道角动量的取值：** $\hat{L}^2 = \lambda\hbar^2 = l(l+1)\hbar^2$，$\hat{L}^2Y = \lambda\hbar^2Y$。

**氢原子轨道角动量 $z$ 方向的取值：** $\hat{L}_z = m\hbar$，$\hat{L}_zY = m\hbar Y$。

**归一化条件：**

$$\int_0^\infty |u_{nl}(r)|^2 dr = \int_0^\infty |R_{nl}(r)|^2 r^2 dr = 1$$

$$\int_0^{2\pi}\int_0^\pi\int_0^\infty \psi_{nlm}^*(r,\theta,\varphi)\psi_{nlm}(r,\theta,\varphi) r^2\sin\theta\,dr\,d\theta\,d\varphi = \delta_{nn'}\delta_{ll'}\delta_{mm'}$$

**能级简并：** $n = n_r + l + 1$，能级简并度 $f_n = \sum_{l=0}^{n-1}(2l+1) = n^2$。

**径向位置概率分布：** 在 $(r, r+dr)$ 内概率为：

$$r^2dr\int_0^{2\pi}\int_0^\pi |\psi_{nlm}(r,\theta,\varphi)|^2\sin\theta\,d\theta\,d\varphi = r^2|R_{nl}(r)|^2dr = |u_{nl}(r)|^2dr$$

$u_{nl}(r)$ 的节点数为 $n_r = n - l - 1$。$n_r = 0$ 的态称为**圆轨道**，$|u_{nl}(r)|^2$ 极大值位置为 $r_n = n^2a_0$，$a_0 = \frac{\hbar^2}{\mu ke^2}$（玻尔半径）。