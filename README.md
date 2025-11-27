# bazel-cmake-deps-override

Helper utility to override bazel deps with CMake dependency already available in the environment.

This is an extremely preliminary piece of software, that will probably not work in your case. Anyhow, in the following
there are some instructions on how to use it.

## Install

This is a unreleased and experimental pure-Python package. If you do not know how to install it in your environment, you are probably not among the target users.

## Usage

> [!WARNING]
> At the moment the project works only if the CMake packages are installed as part of a `conda`/`pixi` environment. If that is not the case, the script will not be able to work.

> [!WARNING]
> If you use pre-compiled libraries in bazel, you can't anymore assume that they are ABI compatible as you are compiling all of them from source with the same compiler. You need to make sure that all the used pre-compiled libraries and the compilation options you are using in your project are ABI compatible.

> [!WARNING]
> The script is only compatible with Bazel dependencies described with `bazel_dep` calls in `MODULE.bazel` files. It provides no compatibility for older `WORKSPACE`-based bazel workflows.

`bazel-cmake-deps-override` is useful if you want to build a `bazel` C++ project, but you want that some C++ dependencies are not re-compiled by `bazel`, but instead you want it to use the library already installed in your environment, and you want to get the information on the installed libraries via the CMake config files and CMake imported targets.

To use it, navigate to the root of the `bazel` project you want to build, and run `bazel-cmake-deps-override` followed by the list of Bazel modules that you want to override for using CMake imported targets. The script will generate all its file in the `build-cmake-deps-override` folder, and then you can tell bazel to use them by passing the `--bazelrc=./bazel-cmake-deps-overrides/bazelrc` argument before any command.

Example:

~~~bash
cd root_folder_of_bazel_project
bazel-cmake-deps-override osqp eigen catch2
bazel --bazelrc=./bazel-cmake-deps-overrides/bazelrc test //...
~~~

> [!WARNING]
> Warning: at the moment the correct CMake and conda metadata is only provided for `osqp`, `eigen` and `catch2` Bazel modules. For any other module called `{bazel_module}`, the script just assumes that there is a CMake package called `{bazel_module}`, that defines a single imported target `{bazel_module}::{bazel_module}`, and that is contained in the `conda` package `{bazel_module}`. The plan is to make this metadata information configurable via a config file.

## FAQs

Q: Why is something like that required at all?
A: See https://github.com/bazelbuild/bazel/issues/20947 and https://github.com/bazelbuild/bazel/discussions/20581 for some related Bazel issues.

Q: Why are you using an external Python script, instead of doing this inside `bazel` itself?
A: I have no idea how to do that inside bazel itself, if you have any suggestion feel free to open an issue!


