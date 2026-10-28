"""CPU rendering requires actual ELF support and excludes the failing WSL path."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rendering_contract_fixture", ROOT / "scripts/capture_gazebo_rendering.py")
rendering = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rendering)


class RenderingContractTests(unittest.TestCase):
    def setUp(self):
        self.paths = ["/usr/lib/x86_64-linux-gnu/dri/swrast_dri.so", "/usr/lib/x86_64-linux-gnu/libLLVM-15.so.1"]
        self.environment = dict(rendering.CPU_ENVIRONMENT)

    def test_cpu_requires_actual_swrast_and_llvm(self):
        self.assertEqual(rendering.rendering_contract_issues("llvmpipe", self.environment, self.paths), [])
        self.assertIn("missing_actual_swrast_dri", rendering.rendering_contract_issues("llvmpipe", self.environment, self.paths[1:]))
        self.assertIn("missing_actual_llvm", rendering.rendering_contract_issues("llvmpipe", self.environment, self.paths[:1]))
        self.assertEqual(rendering.rendering_contract_issues("llvmpipe", self.environment, []), ["rendering_libraries_not_initialized"])

    def test_cpu_rejects_actual_d3d12_despite_declared_cpu_environment(self):
        for extra in ("/usr/lib/wsl/lib/libd3d12core.so", "/usr/lib/wsl/lib/libd3d12.so",
                      "/usr/lib/wsl/drivers/intel/libLLVM-14.so"):
            self.assertIn("unexpected_actual_wsl_d3d12_driver",
                          rendering.rendering_contract_issues("llvmpipe", self.environment, self.paths + [extra]))

    def test_missing_environment_is_not_inferred_from_library_names(self):
        self.assertTrue(rendering.rendering_contract_issues("llvmpipe", {}, self.paths))
        self.assertEqual(rendering.rendering_contract_issues("auto", {}, self.paths + ["/usr/lib/wsl/lib/libd3d12.so"]), [])


if __name__ == "__main__":
    unittest.main()
