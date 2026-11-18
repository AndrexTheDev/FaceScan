import tempfile
import unittest
from pathlib import Path

import numpy as np
from compare_landmarks import compare, fit_similarity, read_obj, read_reference


class ValidationTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(12345)
        self.vertices = rng.normal(size=(468, 3))
        theta = 0.7
        self.rotation = np.array([[np.cos(theta), -np.sin(theta), 0],
                                  [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])
        self.truth = 67.0 * (self.vertices @ self.rotation) + np.array([3., -4., 12.])
        self.rows = [(i, self.truth[i].tolist(), "fit" if i < 8 else "holdout") for i in range(12)]

    def test_scale_rotation_translation_and_holdout(self):
        result = compare(self.vertices, self.rows)
        self.assertAlmostEqual(result["scale_mm_per_eyespace_unit_fitted"], 67, places=8)
        self.assertLess(result["fit"]["max_mm"], 1e-10)
        self.assertLess(result["holdout"]["max_mm"], 1e-10)

    def test_holdout_error_is_not_used_for_fit(self):
        rows = list(self.rows)
        idx, xyz, role = rows[8]
        rows[8] = (idx, [xyz[0] + 10, xyz[1], xyz[2]], role)
        result = compare(self.vertices, rows)
        self.assertLess(result["fit"]["max_mm"], 1e-10)
        self.assertAlmostEqual(result["holdout"]["max_mm"], 10, places=8)

    def test_rejects_insufficient_and_degenerate_and_reflections(self):
        with self.assertRaises(ValueError): compare(self.vertices, self.rows[:9])
        collinear = np.array([[n, 0., 0.] for n in range(5)])
        with self.assertRaises(ValueError): fit_similarity(collinear, collinear)
        scale, rotation, _ = fit_similarity(self.vertices[:8], self.vertices[:8] * [-1, 1, 1])
        self.assertGreater(scale, 0)
        self.assertAlmostEqual(np.linalg.det(rotation), 1, places=10)

    def test_file_reading_and_bad_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            obj = Path(td) / "synthetic.obj"
            obj.write_text("\n".join("v {} {} {}".format(*p) for p in self.vertices))
            csv = Path(td) / "synthetic.csv"
            csv.write_text("landmark,x_mm,y_mm,z_mm,role\n" + "\n".join(
                f"{i},{v[0]},{v[1]},{v[2]},{role}" for i, v, role in self.rows))
            self.assertLess(compare(read_obj(obj), read_reference(csv))["holdout"]["max_mm"], 1e-8)
            csv.write_text(csv.read_text() + "\n0,0,0,0,fit\n")
            with self.assertRaises(ValueError): read_reference(csv)
            obj.write_text("v nan 0 0\n")
            with self.assertRaises(ValueError): read_obj(obj)


if __name__ == "__main__": unittest.main()
