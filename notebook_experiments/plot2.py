from sklearn.metrics import roc_curve, auc, confusion_matrix, ConfusionMatrixDisplay
from sklearn.preprocessing import label_binarize
import matplotlib.pyplot as plt
import numpy as np

def plot_confusion_matrix(y_real, y_pred, class_names=None, save_path=None):
    if y_real.shape[0] != y_pred.shape[0]:
        raise ValueError("y_real and y_pred are not aligned")

    cm = confusion_matrix(y_real, y_pred)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=class_names)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.grid(False)
    disp.plot(ax=ax, cmap="Blues")
    ax.set_title("Matriz de confusión del modelo")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, format="png", dpi=600)
    plt.close(fig)
    return fig



def plot_roc_curve(y_real, y_score, class_names=None, save_path=None):
    # y_real: valores verdaderos (clases)
    # y_score: matriz de probabilidades, de shape (n_samples, n_classes)
    n_classes = y_score.shape[1]

    # Binarizamos los labels
    y_real_bin = label_binarize(y_real, classes=np.arange(n_classes))

    fig = plt.figure(figsize=(8, 6))

    for i in range(n_classes):
        fpr, tpr, _ = roc_curve(y_real_bin[:, i], y_score[:, i])
        roc_auc = auc(fpr, tpr)
        label = f"Clase {i} (AUC = {roc_auc:.2f})" if not class_names else f"{class_names[i]} (AUC = {roc_auc:.2f})"
        plt.plot(fpr, tpr, lw=2, label=label)

    plt.plot([0, 1], [0, 1], linestyle='--', color='gray', lw=2)
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel("Tasa de falsos positivos", fontsize=14)
    plt.ylabel("Tasa de verdaderos positivos", fontsize=14)
    plt.title("Curva ROC multiclase", fontsize=16)
    plt.legend(loc="lower right")
    plt.grid(True)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, format="png", dpi=600)
    plt.close(fig)
    return fig