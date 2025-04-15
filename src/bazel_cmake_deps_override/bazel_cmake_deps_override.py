import os
import sys
import subprocess
import tempfile
import argparse
import toml
import glob
import json

def create_symlink(source, dest):
    """
    Create a symbolic link from dest to source.
    If dest exists, it will be removed.
    """
    dest_dir = os.path.dirname(dest)
    os.makedirs(dest_dir, exist_ok=True)

    if os.path.lexists(dest):
        os.remove(dest)

    try:
        os.symlink(source, dest)
    except Exception as e:
        print(f"Error linking {dest} --> {source}: {e}")

def find_package_json(conda_prefix, package_name):
    """
    Searches for a JSON file for the specified package inside $CONDA_PREFIX/conda-meta.
    The file is assumed to have a name starting with package_name and ending with .json.
    Returns the full path to the first match found.
    """
    meta_dir = os.path.join(conda_prefix, "conda-meta")
    pattern = os.path.join(meta_dir, f"{package_name}-*.json")
    matches = glob.glob(pattern)
    if not matches:
        sys.exit(f"No JSON metadata file found for package '{package_name}' in {meta_dir}.")
    if len(matches) > 1:
        print(f"Warning: Multiple JSON files found for package '{package_name}'. Using the first one: {matches[0]}")
    return os.path.abspath(matches[0])

def process_json(json_path, target_dir, conda_prefix):
    """
    Load the JSON file and symlink each file listed in the "files" key.
    The source files are assumed to be in the conda_prefix.
    """
    try:
        with open(json_path, "r") as fp:
            data = json.load(fp)
    except Exception as e:
        sys.exit(f"Error reading JSON file {json_path}: {e}")

    if "files" not in data:
        sys.exit("JSON file does not contain a 'files' key.")

    file_list = data["files"]

    for rel_path in file_list:
        src = os.path.join(conda_prefix, rel_path)
        dest = os.path.join(target_dir, rel_path)

        if not os.path.exists(src):
            print(f"WARNING: Source file does not exist: {src}")
            continue

        create_symlink(src, dest)

def get_include_files_list(json_path, conda_prefix):
    """
    Load the JSON file and symlink each file listed in the "files" key.
    The source files are assumed to be in the conda_prefix.
    """
    try:
        with open(json_path, "r") as fp:
            data = json.load(fp)
    except Exception as e:
        sys.exit(f"Error reading JSON file {json_path}: {e}")

    if "files" not in data:
        sys.exit("JSON file does not contain a 'files' key.")

    file_list = data["files"]

    # Only get files under the include/ directories (or Library/include/ for Windows compatibility)
    include_list = []
    for rel_path in file_list:
        rel_path = rel_path.removeprefix(conda_prefix).lstrip('/')
        if rel_path.startswith("include/") or rel_path.startswith("Library/include/"):
            include_list.append(rel_path)

    return include_list

def get_include_dir_list(cmake_target_info, conda_prefix):
    """
    Get the include directories from the CMake target info.
    The include directories are assumed to be in the conda_prefix.
    """
    include_dir_list = []
    if "interface_include_directories" in cmake_target_info.keys():
        for inc_dir in cmake_target_info['interface_include_directories']:
            # Strip the prefix from the path, as the bazel modules want the path relative to the module
            inc_dir = inc_dir.removeprefix(conda_prefix).lstrip('/')
            include_dir_list.append(inc_dir)
    return include_dir_list

def get_library_locations(cmake_target_info, conda_prefix):
    """
    Get the library locations from the CMake target info.
    The library locations are assumed to be in the conda_prefix.
    """
    library_location = []
    if "library_location" in cmake_target_info.keys():
        for lib in cmake_target_info['library_location']:
            # Strip the prefix from the path, as the bazel modules want the path relative to the module

            lib = lib.removeprefix(conda_prefix).lstrip('/')
            library_location.append(lib)
    return library_location

def convert_bazel_module_to_cmake_package_and_target(bazel_modules):
    bazel2cmake_map = {}

    for module in bazel_modules:
        bazel2cmake_el = {}

        if module == "eigen":
            # The bazel module eigen is mapped to the CMake package Eigen3 and the CMake target Eigen3::Eigen3.
            bazel2cmake_el['cmake_package'] = 'Eigen3'
            bazel2cmake_el['targets'] = [('Eigen3::Eigen', "eigen")]
            bazel2cmake_el['conda_package'] = 'eigen'
        elif module == "catch2":
            # The bazel module catch is mapped to the CMake package Catch2 and the CMake target Catch2::Catch2.
            bazel2cmake_el['cmake_package'] = 'Catch2'
            bazel2cmake_el['targets'] = [('Catch2::Catch2WithMain',"catch2_main"), ('Catch2::Catch2',"catch2")]
            bazel2cmake_el['conda_package'] = 'catch2'
        elif module == "osqp":
            # The bazel module catch is mapped to the CMake package Catch2 and the CMake target Catch2::Catch2.
            bazel2cmake_el['cmake_package'] = 'osqp'
            bazel2cmake_el['targets'] = [('osqp::osqp',"osqp")]
            bazel2cmake_el['conda_package'] = 'libosqp'
        else:
            # By default, the bazel module foo is mapped to the CMake package foo and the CMake target foo::foo.
            bazel2cmake_el['cmake_package'] = module
            bazel2cmake_el['targets'] = [(f"{module}::{module}", module)]
            bazel2cmake_el['conda_package'] = module


        bazel2cmake_map[module] = bazel2cmake_el

    return bazel2cmake_map

def parse_toml_file(filename):
    try:
        with open(filename, 'r') as file:
            data = toml.load(file)
        return data
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
    except toml.TomlDecodeError as e:
        print(f"Error decoding TOML: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def get_bazel_target_from_cmake_target_name(cmake_target_name, bazel2cmake_map):
    for bazel_mod in bazel2cmake_map:
        for target_couple in bazel2cmake_map[bazel_mod]['targets']:
            if target_couple[0] == cmake_target_name:
                return bazel_mod, target_couple[1]
    return None, None

def get_target_info_from_cmake_target_name(cmake_target_name, target_properties):
    for target in target_properties['targets']:
        if target['cmake_target_name'] == cmake_target_name:
            return target
    return None

def generate_cc_library_code(bazel_mod, bazel_target, cmake_target_name, target_properties, bazel2cmake_map, conda_prefix, f):
    cmake_target_info = get_target_info_from_cmake_target_name(cmake_target_name, target_properties)
    bazel_mod, bazel_target = get_bazel_target_from_cmake_target_name(cmake_target_name, bazel2cmake_map)
    f.write(f'cc_library(\n')
    f.write(f'    name = "{bazel_target}",\n')
    if "interface_include_directories" in cmake_target_info.keys():
        hdrs_list = get_include_files_list(bazel2cmake_map[bazel_mod]['conda_json'] , conda_prefix)
        f.write(f'    hdrs = {str(hdrs_list)},\n')
        includes_list = get_include_dir_list(cmake_target_info, conda_prefix)
        f.write(f'    includes = {str(includes_list)},\n')
    if "interface_compile_definitions" in cmake_target_info.keys():
        f.write(f'    defines = {str(cmake_target_info["interface_compile_definitions"])},\n')
    if "library_location" in cmake_target_info.keys():
        lib_list = get_library_locations(cmake_target_info, conda_prefix)
        f.write(f'    srcs = {str(lib_list)},\n')
    f.write(f'    visibility = ["//visibility:public"],\n')

    # Handle dependencies. We convert CMake targets to bazel targets,
    # and we handle the case where the dependent target belongs to another bazel module
    if "interface_link_libraries_targets" in cmake_target_info.keys():
        f.write(f'    deps = [')
        for dep in cmake_target_info['interface_link_libraries_targets']:
            dep_bazel_mod, dep_bazel_target = get_bazel_target_from_cmake_target_name(dep, bazel2cmake_map)
            if dep_bazel_mod == bazel_mod:
                f.write(f'":{dep_bazel_target}",')
            else:
                f.write(f'"@{dep_bazel_mod}//:{dep_bazel_target}",')
        f.write(f'],\n')
    f.write(f')\n')
    f.write(f'\n')


def bazel_cmake_deps_override(bazel_modules):
    bazel2cmake_map = convert_bazel_module_to_cmake_package_and_target(bazel_modules)

    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()

    cmake_packages = []
    cmake_targets = []
    for el in bazel2cmake_map:
        cmake_packages.append(bazel2cmake_map[el]['cmake_package'])
        for target_couple in bazel2cmake_map[el]['targets']:
            cmake_target_name = target_couple[0]
            cmake_targets.append(cmake_target_name)

    try:
        # Copy the templates/CMakeLists.txt file to the temporary directory
        from importlib import resources

        # Assuming the file is in the 'templates' subpackage of 'cmake_package_check'
        with resources.open_text('bazel_cmake_deps_override.templates', 'CMakeLists.txt') as f:
            cmake_content = f.read()

        os.chdir(temp_dir)
        with open('CMakeLists.txt', 'w') as f:
            f.write(cmake_content)

        # Convert package and targets to a CMake list
        cmake_package_list = ';'.join(cmake_packages)
        cmake_target_list = ';'.join(cmake_targets)

        # Run CMake in the temporary directory
        print("===================================")
        print("=== CMake configure output:        ")
        print("===================================")
        subprocess.run(['cmake','-GNinja','-S.', '-B.',f'-DBCPO_CMAKE_PACKAGES={cmake_package_list}',f'-DBCPO_CMAKE_TARGETS={cmake_target_list}'], cwd=temp_dir, check=True)

        # parse the generated json file
        toml_file = os.path.join(temp_dir, 'bcpo_target_properties.toml')
        target_properties = parse_toml_file(toml_file)

    except subprocess.CalledProcessError as e:
        print(f"Error occurred: {e}")
        return False

    # At this point, use the data generated in bcpo_target_properties.toml to generate the .bazerc_cmake_local_overrides file
    # and the bazel-cmake-deps-overrides/ directory.
    # The files should be generated in the current working directory.

    #

    # Create the bazel-cmake-deps-overrides directory
    os.chdir(original_cwd)
    os.makedirs(os.path.join(os.getcwd(),'bazel-cmake-deps-overrides'), exist_ok=True)
    print(f"Created {os.path.join(os.getcwd(),'bazel-cmake-deps-overrides')} folder")
    # Generate the files from the temporary directory to the bazel-cmake-deps-overrides directory
    for bazel_mod in bazel_modules:
        # Create folder
        bazel_mod_dir = os.path.join('bazel-cmake-deps-overrides', bazel_mod)
        os.makedirs(bazel_mod_dir, exist_ok=True)

        # Symlink the content of the conda package to the module, as bazel only supports files specified
        # in the same folder of the MODULE.bazel file
        conda_package = bazel2cmake_map[bazel_mod]['conda_package']
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if not conda_prefix:
            sys.exit("Error: CONDA_PREFIX environment variable is not set. Run this script inside a conda environment.")

        # Get the JSON file automatically from $CONDA_PREFIX/conda-meta based on the provided package name.
        package_json = find_package_json(conda_prefix, conda_package)
        bazel2cmake_map[bazel_mod]['conda_json'] = package_json

        json_file = os.path.abspath(package_json)

        process_json(bazel2cmake_map[bazel_mod]['conda_json'], bazel_mod_dir, conda_prefix)

        # Generate MODULE.bazel file
        module_bazel = os.path.join(bazel_mod_dir, 'MODULE.bazel')
        with open(module_bazel, 'w') as f:
            f.write("# This file is generated by bazel-cmake-deps-override utility\n")
            f.write("# Do not edit this file manually\n")
            f.write("module(\n")
            f.write(f"    name = \"{bazel_mod}\",\n")
            f.write(")\n")
            f.write("\n")
            f.write('bazel_dep(name = "rules_cc", version = "0.1.1")\n')

        print(f"Generated file {module_bazel}")

        # Generate BUILD.bazel file
        build_bazel = os.path.join(bazel_mod_dir, 'BUILD.bazel')

        with open(build_bazel, 'w') as f:
            f.write("# This file is generated by bazel-cmake-deps-override utility\n")
            f.write("# Do not edit this file manually\n")
            f.write('\n')
            f.write('load("@rules_cc//cc:defs.bzl", "cc_library")\n')
            f.write('\n')
            # Here we add a cc_library for each target
            for target in bazel2cmake_map[bazel_mod]['targets']:
                generate_cc_library_code(bazel_mod, target[1], target[0], target_properties, bazel2cmake_map, conda_prefix, f)

        print(f"Generated file {build_bazel}")


    bazelrc_file = os.path.join(os.getcwd(), 'bazel-cmake-deps-overrides', 'bazelrc')
    with open(bazelrc_file, 'w') as f:
        f.write("# This file is generated by bazel-cmake-deps-override utility\n")
        f.write("# Do not edit this file manually\n")
        f.write("\n")
        f.write("# Local overrides for CMake imported targets\n")
        for bazel_mod in bazel_modules:
            f.write(f"common --override_module={bazel_mod}=./bazel-cmake-deps-overrides/{bazel_mod}\n")

    # If all is ok, return true
    return True


def main():
    parser = argparse.ArgumentParser(description="Utility to generate bazel modules to pass as local_overrides to use CMake imported targets in bazel.")
    parser.add_argument("bazel_modules", metavar="bazel_modules", type=str, nargs="+", help="Names of the bazel modules that should be overriden by CMake imported targets")

    args = parser.parse_args()
    result = bazel_cmake_deps_override(args.bazel_modules)

    if(result):
        print("bazel-cmake-deps-override: Successfully generated. Please run 'bazel --bazelrc=./bazel-cmake-deps-overrides/bazelrc <command>' to use the project with the override to use CMake imported targets")
        sys.exit(0)
    else:
        print("bazel-cmake-deps-override: FAILURE.")
        sys.exit(1)

if __name__ == "__main__":
    main()
