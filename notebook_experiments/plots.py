import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

from sklearn.feature_selection import mutual_info_classif

def plot_histograms(data, col, save_path=None):

    classes = data['class'].unique()


    fig = plt.figure(figsize=(8, 6))

    # Plot histograms for each class
    for cls in classes:
        subset = data[data['class'] == cls]
        if col == 'redshift':
            plt.hist(subset[col], bins=50, alpha=0.5, label=f"Class {cls}", density = False)
        else:
            plt.hist(subset[col], bins=50, alpha=0.5, label=f"Class {cls}", density = True)

    plt.title(f"Histogram of {col} by Class")
    plt.xlabel(col)
    plt.ylabel("Frequency")
    if col == 'u':
        plt.xlim(0, 50)
    elif col == 'g':
        plt.xlim(0, 50)XS
    elif col == 'z':
        plt.xlim(0, 50)
    elif col == 'redshift':
        plt.xlim(-1, 5)
    plt.legend()

    # Grabamos el gráfico si save_path es especificado
    if save_path:
        plt.savefig(save_path, format="png", dpi=600)

    # Prevemos que Matplotlib de mostrar el gráfico cada vez que llamamos a la función
    plt.close(fig)

    return fig
