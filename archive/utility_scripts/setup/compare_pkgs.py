import pkg_resources
import sys
from pathlib import Path

def get_installed_packages():
    return {pkg.key: pkg.version for pkg in pkg_resources.working_set}

def parse_requirements(req_path):
    with open(req_path, 'r', encoding='utf-8-sig') as f:
        return list(pkg_resources.parse_requirements(f))

def compare_packages():
    req_path = Path('requirements.txt')
    if not req_path.exists():
        print("requirements.txt not found")
        return

    installed = get_installed_packages()
    requirements = parse_requirements(req_path)

    missing = []
    version_mismatch = []
    extra = []

    req_names = set()

    for req in requirements:
        req_names.add(req.key)
        if req.key not in installed:
            missing.append(str(req))
        else:
            installed_ver = installed[req.key]
            # Simple check if version is specified
            if req.specs:
                # This is a basic check, pkg_resources has more complex spec matching
                # but for this purpose, we just want to see if it satisfies
                if not req.__contains__(installed_ver):
                     version_mismatch.append(f"{req.key}: installed {installed_ver}, required {req}")

    for pkg_name, pkg_ver in installed.items():
        if pkg_name not in req_names:
            extra.append(f"{pkg_name}=={pkg_ver}")

    print("--- Missing Packages (in requirements.txt but not installed) ---")
    for p in missing:
        print(p)
    
    print("\n--- Version Mismatches ---")
    for p in version_mismatch:
        print(p)

    print("\n--- Extra Packages (installed but not in requirements.txt) ---")
    for p in extra:
        print(p)

if __name__ == "__main__":
    compare_packages()
