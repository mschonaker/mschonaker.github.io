import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;

// Principal component analysis for float vectors.
// fit() runs a cyclic Jacobi eigendecomposition on the covariance matrix.
public class Pca {

    public final double[] mean;         // d values
    public final double[][] components; // k x d rows; project is (x - mean) dot row
    public final double[] eigenvalues;  // all d eigenvalues, descending (empty for loaded files)

    private Pca(double[] mean, double[][] components, double[] eigenvalues) {
        this.mean = mean;
        this.components = components;
        this.eigenvalues = eigenvalues;
    }

    public static Pca fit(float[][] data, int k) {
        int n = data.length;
        int d = data[0].length;

        double[] mean = new double[d];
        for (float[] row : data) {
            for (int j = 0; j < d; j++) {
                mean[j] += row[j];
            }
        }
        for (int j = 0; j < d; j++) {
            mean[j] /= n;
        }

        double[][] cov = new double[d][d];
        for (float[] row : data) {
            for (int j = 0; j < d; j++) {
                double xj = row[j] - mean[j];
                for (int l = j; l < d; l++) {
                    cov[j][l] += xj * (row[l] - mean[l]);
                }
            }
        }
        for (int j = 0; j < d; j++) {
            for (int l = j; l < d; l++) {
                cov[j][l] /= (n - 1);
                cov[l][j] = cov[j][l];
            }
        }

        double[][] vecs = new double[d][d];
        for (int j = 0; j < d; j++) {
            vecs[j][j] = 1;
        }
        jacobi(cov, vecs);

        Integer[] order = new Integer[d];
        for (int j = 0; j < d; j++) {
            order[j] = j;
        }
        Arrays.sort(order, (x, y) -> Double.compare(cov[y][y], cov[x][x]));

        double[] eigenvalues = new double[d];
        double[][] components = new double[k][d];
        for (int i = 0; i < k; i++) {
            eigenvalues[i] = cov[order[i]][order[i]];
            for (int j = 0; j < d; j++) {
                components[i][j] = vecs[j][order[i]];
            }
        }
        return new Pca(mean, components, eigenvalues);
    }

    public double explainedVarianceRatio(int k) {
        double total = 0;
        double kept = 0;
        for (int i = 0; i < eigenvalues.length; i++) {
            total += eigenvalues[i];
            if (i < k) {
                kept += eigenvalues[i];
            }
        }
        return kept / total;
    }

    // Cyclic Jacobi rotations. The same rotations are applied to vecs so its
    // columns track the eigenvectors while cov converges toward a diagonal.
    private static void jacobi(double[][] a, double[][] vecs) {
        int d = a.length;
        for (int sweep = 0; sweep < 64; sweep++) {
            double off = 0;
            double diag = 0;
            for (int p = 0; p < d; p++) {
                diag += a[p][p] * a[p][p];
                for (int q = p + 1; q < d; q++) {
                    off += a[p][q] * a[p][q];
                }
            }
            if (off < 1e-16 * diag) {
                break;
            }
            for (int p = 0; p < d - 1; p++) {
                for (int q = p + 1; q < d; q++) {
                    if (Math.abs(a[p][q]) < 1e-15) {
                        continue;
                    }
                    double theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
                    double t = Math.signum(theta) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
                    double c = 1 / Math.sqrt(t * t + 1);
                    double s = t * c;

                    for (int i = 0; i < d; i++) {
                        double aip = a[i][p];
                        double aiq = a[i][q];
                        a[i][p] = c * aip - s * aiq;
                        a[i][q] = s * aip + c * aiq;
                    }
                    for (int j = 0; j < d; j++) {
                        double apj = a[p][j];
                        double aqj = a[q][j];
                        a[p][j] = c * apj - s * aqj;
                        a[q][j] = s * apj + c * aqj;
                    }
                    for (int i = 0; i < d; i++) {
                        double vip = vecs[i][p];
                        double viq = vecs[i][q];
                        vecs[i][p] = c * vip - s * viq;
                        vecs[i][q] = s * vip + c * viq;
                    }
                }
            }
        }
    }

    public float[] project(float[] x) {
        int k = components.length;
        int d = mean.length;
        float[] y = new float[k];
        for (int i = 0; i < k; i++) {
            double sum = 0;
            double[] row = components[i];
            for (int j = 0; j < d; j++) {
                sum += row[j] * (x[j] - mean[j]);
            }
            y[i] = (float) sum;
        }
        return y;
    }

    public void save(Path file) throws IOException {
        StringBuilder sb = new StringBuilder();
        sb.append(components.length).append(' ').append(mean.length).append('\n');
        for (double m : mean) {
            sb.append(m).append(' ');
        }
        sb.append('\n');
        for (double[] row : components) {
            for (double v : row) {
                sb.append(v).append(' ');
            }
            sb.append('\n');
        }
        Files.writeString(file, sb.toString());
    }

    public static Pca load(Path file) throws IOException {
        List<String> lines = Files.readAllLines(file);
        String[] head = lines.get(0).split(" ");
        int k = Integer.parseInt(head[0]);
        int d = Integer.parseInt(head[1]);
        double[] mean = new double[d];
        String[] ms = lines.get(1).trim().split("\\s+");
        for (int j = 0; j < d; j++) {
            mean[j] = Double.parseDouble(ms[j]);
        }
        double[][] components = new double[k][d];
        for (int i = 0; i < k; i++) {
            String[] cs = lines.get(2 + i).trim().split("\\s+");
            for (int j = 0; j < d; j++) {
                components[i][j] = Double.parseDouble(cs[j]);
            }
        }
        return new Pca(mean, components, new double[0]);
    }

    // Wrap an already computed mean + top-k component matrix as a Pca.
    public static Pca reconstruct(double[] mean, double[][] components) {
        return new Pca(mean, components, new double[0]);
    }
}
