from __future__ import annotations

import unittest

from panelsolver.app.environment import (
    resolve_parallel_chunk_environment,
    resolve_shielding_environment,
)
from panelsolver.core import SchedulerError, ShieldingConfig, ShieldingError


class EnvironmentResolutionTests(unittest.TestCase):
    def test_shielding_batch_precedence_is_explicit_environment_default(self) -> None:
        environment = {"PANELSOLVER_SHIELD_BATCH_SIZE": "5"}
        resolved = resolve_shielding_environment(
            ShieldingConfig(),
            environment=environment,
        )
        self.assertEqual(5, resolved.batch_size)

        explicit = resolve_shielding_environment(
            ShieldingConfig(batch_size=2),
            environment=environment,
        )
        self.assertEqual(2, explicit.batch_size)

        configured = resolve_shielding_environment(
            ShieldingConfig(),
            environment={"PANELSOLVER_SHIELD_BATCH_SIZE": "6"},
        )
        self.assertEqual(6, configured.batch_size)

        defaults = resolve_shielding_environment(
            ShieldingConfig(),
            environment={},
        )
        self.assertIsNone(defaults.batch_size)

    def test_invalid_shielding_environment_names_the_boundary_variable(self) -> None:
        for name, value in (("PANELSOLVER_SHIELD_BATCH_SIZE", "0"),):
            with (
                self.subTest(name=name, value=value),
                self.assertRaisesRegex(ShieldingError, name),
            ):
                resolve_shielding_environment(
                    ShieldingConfig(),
                    environment={name: value},
                )

    def test_shield_cache_capacity_environment_is_not_recognized(self) -> None:
        resolved = resolve_shielding_environment(
            ShieldingConfig(),
            environment={
                "PANELSOLVER_SHIELD_CACHE_MAX": "invalid",
            },
        )
        self.assertIsNone(resolved.batch_size)
        self.assertFalse(hasattr(resolved, "cache_max"))

    def test_shielding_environment_is_ignored_when_shielding_is_disabled(self) -> None:
        config = ShieldingConfig(enabled=False)
        resolved = resolve_shielding_environment(
            config,
            environment={"PANELSOLVER_SHIELD_BATCH_SIZE": "invalid"},
        )
        self.assertIs(config, resolved)

    def test_chunk_precedence_is_explicit_environment_default(self) -> None:
        environment = {"PANELSOLVER_PARALLEL_CHUNK_CASES": "3"}
        self.assertEqual(
            2,
            resolve_parallel_chunk_environment(
                2,
                environment=environment,
            ),
        )
        self.assertEqual(
            3,
            resolve_parallel_chunk_environment(
                environment=environment,
            ),
        )
        self.assertEqual(
            8,
            resolve_parallel_chunk_environment(
                environment={},
            ),
        )

    def test_invalid_chunk_environment_is_explicit(self) -> None:
        with self.assertRaisesRegex(SchedulerError, "PANELSOLVER"):
            resolve_parallel_chunk_environment(
                environment={"PANELSOLVER_PARALLEL_CHUNK_CASES": "0"},
            )

    def test_removed_product_environment_names_are_ignored(self) -> None:
        environment = {
            "FMFSOLVER_SHIELD_BATCH_SIZE": "3",
            "NEWTSOLVER_PARALLEL_CHUNK_CASES": "5",
        }
        self.assertIsNone(
            resolve_shielding_environment(
                ShieldingConfig(), environment=environment
            ).batch_size
        )
        self.assertEqual(
            8,
            resolve_parallel_chunk_environment(environment=environment),
        )


if __name__ == "__main__":
    unittest.main()
