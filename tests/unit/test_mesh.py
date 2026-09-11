import pickle
import unittest

import numpy as np

from panelsolver.core import (
    ContractValueError,
    MeshComponent,
    PanelGeometry,
    PanelMesh,
    ShapeError,
)


def geometry(*, component_ids: object = (0, 1)) -> PanelGeometry:
    return PanelGeometry(
        centers_stl_m=[[0.25, 0.25, 0.0], [0.75, 0.75, 0.0]],
        normals_out_stl=[[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]],
        areas_m2=[0.5, 0.5],
        component_ids=component_ids,
    )


def components() -> list[MeshComponent]:
    return [
        MeshComponent(1, "second.stl", {"label": "second"}),
        MeshComponent(0, "first.stl", {"label": "first"}),
    ]


class PanelMeshTests(unittest.TestCase):
    def test_mesh_owns_topology_and_aligns_components(self) -> None:
        vertices = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        )
        faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int16)
        mesh = PanelMesh(vertices, faces, geometry(), components())

        vertices[:] = 99.0
        faces[:] = 0
        np.testing.assert_array_equal(
            mesh.vertices_stl_m,
            np.array(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [1.0, 1.0, 0.0],
                ]
            ),
        )
        np.testing.assert_array_equal(mesh.faces, [[0, 1, 2], [1, 3, 2]])
        np.testing.assert_array_equal(mesh.face_component_ids, [0, 1])
        self.assertEqual((0, 1), tuple(c.component_id for c in mesh.components))
        self.assertEqual(4, mesh.n_vertices)
        self.assertEqual(2, mesh.n_faces)
        self.assertEqual(np.dtype(np.float64), mesh.vertices_stl_m.dtype)
        self.assertEqual(np.dtype(np.int64), mesh.faces.dtype)
        self.assertFalse(mesh.vertices_stl_m.flags.writeable)
        self.assertFalse(mesh.faces.flags.writeable)

    def test_pickle_preserves_topology_immutability(self) -> None:
        mesh = PanelMesh(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]],
            [[0, 1, 2], [1, 3, 2]],
            geometry(),
            components(),
        )
        restored = pickle.loads(pickle.dumps(mesh))
        self.assertFalse(restored.vertices_stl_m.flags.writeable)
        self.assertFalse(restored.faces.flags.writeable)
        self.assertEqual("first", restored.components[0].metadata["label"])

    def test_mesh_rejects_invalid_arrays_and_indices(self) -> None:
        valid_vertices = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]]
        valid_faces = [[0, 1, 2], [1, 3, 2]]
        with self.assertRaises(ShapeError):
            PanelMesh([[0, 0]], valid_faces, geometry(), components())
        with self.assertRaises(ContractValueError):
            PanelMesh(np.empty((0, 3)), valid_faces, geometry(), components())
        with self.assertRaises(ContractValueError):
            PanelMesh(valid_vertices, [[0, 1, 4], [1, 3, 2]], geometry(), components())
        with self.assertRaises(ContractValueError):
            PanelMesh(valid_vertices, [[0, 1, 2]], geometry(), components())
        with self.assertRaises(ContractValueError):
            PanelMesh(valid_vertices, valid_faces, object(), components())

    def test_mesh_rejects_component_misalignment_and_duplicates(self) -> None:
        vertices = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]]
        faces = [[0, 1, 2], [1, 3, 2]]
        with self.assertRaises(ContractValueError):
            PanelMesh(
                vertices,
                faces,
                geometry(),
                [MeshComponent(0, "only-first.stl")],
            )
        with self.assertRaises(ContractValueError):
            PanelMesh(
                vertices,
                faces,
                geometry(),
                [MeshComponent(0, "a.stl"), MeshComponent(0, "b.stl")],
            )
        with self.assertRaises(ContractValueError):
            MeshComponent(-1, "bad.stl")
        with self.assertRaises(ContractValueError):
            MeshComponent(0, " bad.stl")


if __name__ == "__main__":
    unittest.main()
