#!/usr/bin/env python
# This Python file uses the following encoding: utf-8

# Recipe Robot
# Copyright 2015 Elliot Jordan, Shea G. Craig
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
recipe-robot.py

Easily and automatically create AutoPkg recipes.

usage: recipe-robot.py [-h] [-v] [-o OUTPUT_DIR] [-t RECIPE_TYPES]
                       [--include-existing] [--config]
                       input_path

positional arguments:
  input_path            Path to a recipe or app from which to derive AutoPkg
                        recipes.

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Generate additional output about the process.
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
                        Path to a folder you'd like to save your generated
                        recipes in.
  -t RECIPE_TYPES, --recipe-types RECIPE_TYPES
                        The types of recipe you'd like to generate.
  --include-existing    Offer to generate recipes even if one already exists
                        on GitHub.
  --config              Adjust Recipe Robot preferences prior to generating
                        recipes.
"""


import argparse
import os.path
import pprint
import random
import re
import shlex
from subprocess import Popen, PIPE
import sys

# TODO(Elliot): Can we use the one at /Library/AutoPkg/FoundationPlist instead?
try:
    import FoundationPlist
except:
    print '[WARNING] importing plistlib as FoundationPlist'
    import plistlib as FoundationPlist


# Global variables.
version = '0.0.2'
verbose_mode = False  # set to True for additional user-facing output
debug_mode = True  # set to True to output everything all the time
prefs_file = os.path.expanduser(
    "~/Library/Preferences/com.elliotjordan.recipe-robot.plist")

# Build the list of download formats we know about.
supported_image_formats = ("dmg", "iso")  # downloading iso unlikely
supported_archive_formats = ("zip", "tar.gz", "gzip", "tar.bz2")
supported_install_formats = ("pkg", "mpkg")  # downloading mpkg unlikely
all_supported_formats = supported_image_formats + supported_archive_formats + supported_install_formats

class bcolors:

    """Specify colors that are used in Terminal output."""

    BOLD = '\033[1m'
    DEBUG = '\033[95m'
    ENDC = '\033[0m'
    ERROR = '\033[91m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    UNDERLINE = '\033[4m'
    WARNING = '\033[93m'


class InputType(object):

    """Python pseudo-enum for describing types of input."""

    (app,
     download_recipe,
     munki_recipe,
     pkg_recipe,
     install_recipe,
     jss_recipe,
     absolute_recipe,
     sccm_recipe,
     ds_recipe) = range(9)


# Use this as a reference to build out the classes below:
# https://github.com/homebysix/recipe-robot/blob/master/DEVNOTES.md


class Recipe(object):

    """A generic AutoPkg recipe class."""

    def create(self):
        """Create a new recipe with required keys set to defaults."""
        self["Identifier"] = ""
        self["Input"] = {}  # dict
        self["Input"]["NAME"] = ""
        self["Process"] = []  # list/array
        self["MinimumVersion"] = "0.5.0"

    def add_input(self, key, value=""):
        """Add or set a recipe input variable."""
        self["Input"][key] = value


class DownloadRecipe(Recipe):

    """A download recipe class. Extends Recipe."""

    def create(self):
        """Create a new recipe with required keys set to defaults."""
        self["Process"].append({
            "Processor": "URLDownloader"
        })


class MunkiRecipe(Recipe):

    """A munki recipe class. Extends Recipe."""

    def create(self):
        """Create a new recipe with required keys set to defaults."""
        self["ParentRecipe"] = ""
        self["Input"]["MUNKI_REPO_SUBDIR"] = ""
        self["Input"]["pkginfo"] = {
            "catalogs": [],
            "description": [],
            "display_name": [],
            "name": [],
            "unattended_install": True
        }
        self["Process"].append({
            "Processor": "MunkiImporter",
            "Arguments": {
                "pkg_path": "%pathname%",
                "repo_subdirectory": "%MUNKI_REPO_SUBDIR%"
            }
        })


class PkgRecipe(Recipe):

    """A pkg recipe class. Extends Recipe."""

    def create(self):
        """Create a new recipe with required keys set to defaults."""
        self["ParentRecipe"] = ""
        self["Input"]["PKG_ID"] = ""
        self["Process"].append({
            "Processor": "PkgRootCreator",
            "Arguments": {
                "pkgroot": "%RECIPE_CACHE_DIR%/%NAME%",
                "pkgdirs": {}
            }
        })
        self["Process"].append({
            "Processor": "Versioner",
            "Arguments": {
                "input_plist_path": "",
                "plist_version_key": ""
            }
        })
        self["Process"].append({
            "Processor": "PkgCreator",
            "Arguments": {
                "pkg_request": {
                    "pkgname": "%NAME%-%version%",
                    "version": "%version%",
                    "id": "",
                    "options": "purge_ds_store",
                    "chown": [{
                        "path": "Applications",
                        "user": "root",
                        "group": "admin"
                    }]
                }
            }
        })


class InstallRecipe(Recipe):

    """An install recipe class. Extends Recipe."""

    def create(self):
        """Create a new recipe with required keys set to defaults."""
        self["ParentRecipe"] = ""


class JSSRecipe(Recipe):

    """A jss recipe class. Extends Recipe."""

    def create(self):
        """Create a new recipe with required keys set to defaults."""
        self["ParentRecipe"] = ""
        self["Input"]["prod_name"] = ""
        self["Input"]["category"] = ""
        self["Input"]["policy_category"] = ""
        self["Input"]["policy_template"] = ""
        self["Input"]["self_service_icon"] = ""
        self["Input"]["self_service_description"] = ""
        self["Input"]["groups"] = []
        self["Input"]["GROUP_NAME"] = ""
        self["Input"]["GROUP_TEMPLATE"] = ""
        self["Process"].append({
            "Processor": "JSSImporter",
            "Arguments": {
                "prod_name": "%NAME%",
                "category": "%CATEGORY%",
                "policy_category": "%POLICY_CATEGORY%",
                "policy_template": "%POLICY_TEMPLATE%",
                "self_service_icon": "%SELF_SERVICE_ICON%",
                "self_service_description": "%SELF_SERVICE_DESCRIPTION%",
                "groups": [{
                    "name": "%GROUP_NAME%",
                    "smart": True,
                    "template_path": "%GROUP_TEMPLATE%"
                }]
            }
        })


class AbsoluteRecipe(Recipe):

    """An absolute recipe class. Extends Recipe."""

    def create(self):
        """Create a new recipe with required keys set to defaults."""
        self["ParentRecipe"] = ""
        self["Process"].append({
            "Processor": "com.github.tburgin.AbsoluteManageExport/AbsoluteManageExport",
            "SharedProcessorRepoURL": "https://github.com/tburgin/AbsoluteManageExport",
            "Arguments": {
                "dest_payload_path": "%RECIPE_CACHE_DIR%/%NAME%-%version%.amsdpackages",
                "sdpackages_ampkgprops_path": "%RECIPE_DIR%/%NAME%-Defaults.ampkgprops",
                "source_payload_path": "%pkg_path%",
                "import_abman_to_servercenter": True
            }
        })


class SCCMRecipe(Recipe):

    """An sccm recipe class. Extends Recipe."""

    def create(self):
        """Create a new recipe with required keys set to defaults."""
        self["ParentRecipe"] = ""
        self["Process"].append({
            "Processor": "com.github.autopkg.cgerke-recipes.SharedProcessors/CmmacCreator",
            "SharedProcessorRepoURL": "https://github.com/autopkg/cgerke-recipes",
            "Arguments": {
                "source_file": "%RECIPE_CACHE_DIR%/%NAME%-%version%.pkg",
                "destination_directory": "%RECIPE_CACHE_DIR%"
            }
        })


class DSRecipe(Recipe):

    """A ds recipe class. Extends Recipe."""

    def create(self):
        """Create a new recipe with required keys set to defaults."""
        self["ParentRecipe"] = ""
        self["Input"]["DS_PKGS_PATH"] = ""
        self["Input"]["DS_NAME"] = ""
        self["Process"].append({
            "Processor": "StopProcessingIf",
            "Arguments": {
                "predicate": "new_package_request == FALSE"
            }
        })
        self["Process"].append({
            "Processor": "Copier",
            "Arguments": {
                "source_path": "%pkg_path%",
                "destination_path": "%DS_PKGS_PATH%/%DS_NAME%.pkg",
                "overwrite": True
            }
        })


# TODO(Elliot or more likely Shea): Once classes are added, rework these
# functions to use classes instead of existing hard-wired logic:
#    - init_recipes
#    - init_prefs
#    - build_prefs
#    - get_input_type
#    - create_existing_recipe_list
#    - create_buildable_recipe_list
#    - handle_app_input
#    - handle_download_recipe_input
#    - handle_munki_recipe_input
#    - handle_pkg_recipe_input
#    - handle_install_recipe_input
#    - handle_jss_recipe_input
#    - handle_absolute_recipe_input
#    - handle_sccm_recipe_input
#    - handle_ds_recipe_input
#    - search_sourceforge_and_github
#    - select_recipes_to_generate
#    - generate_selected_recipes
#    - write_recipe_file

def robo_print(output_type, message):
    """Print the specified message in an appropriate color, and only print
    debug output if debug_mode is True.

    Args:
        output_type: One of "error", "warning", "debug", or "verbose".
        message: String to be printed to output.
    """

    if output_type == "error":
        print >> sys.stderr, bcolors.ERROR, "[ERROR]", message, bcolors.ENDC
        sys.exit(1)
    elif output_type == "warning":
        print >> sys.stderr, bcolors.WARNING, "[WARNING]", message, bcolors.ENDC
    elif output_type == "debug" and debug_mode is True:
        print bcolors.DEBUG, "[DEBUG]", message, bcolors.ENDC
    elif output_type == "verbose":
        if verbose_mode is True or debug_mode is True:
            print message
        else:
            pass
    else:
        print message


def get_exitcode_stdout_stderr(cmd):
    """Execute the external command and get its exitcode, stdout and stderr.

    Args:
        cmd: The single shell command to be executed. No piping allowed.

    Returns:
        exitcode: Zero upon success. Non-zero upon error.
        out: String from standard output.
        err: String from standard error.
    """

    args = shlex.split(cmd)
    proc = Popen(args, stdout=PIPE, stderr=PIPE)
    out, err = proc.communicate()
    exitcode = proc.returncode
    return exitcode, out, err


def build_argument_parser():
    """Build and return the argument parser for Recipe Robot.

    Returns:
        Parser object.
    """

    parser = argparse.ArgumentParser(
        description="Easily and automatically create AutoPkg recipes.")
    parser.add_argument(
        "input_path",
        help="Path from which to derive AutoPkg recipes. This can be one of "
             "the following: existing app, existing AutoPkg recipe, input "
             "plist, GitHub or SourceForge URL, or direct download URL.")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Generate additional output about the process.")
    parser.add_argument(
        "-o", "--output-dir",
        action="store",
        help="Path to a folder you'd like to save your generated recipes in.")
    parser.add_argument(
        "-t", "--recipe-types",
        action="store",
        help="The types of recipe you'd like to generate.")
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Offer to generate recipes even if one already exists on GitHub.")
    parser.add_argument(
        "--config",
        action="store_true",
        help="Adjust Recipe Robot preferences prior to generating recipes.")
    return parser


def print_welcome_text():
    """Print the text that people see when they first start Recipe Robot."""

    welcome_text = """%s%s
                      -----------------------------------
                     |  Welcome to Recipe Robot v%s.  |
                      -----------------------------------
                                \   _[]_
                                 \  [oo]
                                   d-||-b
                                     ||
                                   _/  \_
    """ % (bcolors.DEBUG, bcolors.ENDC, version)

    robo_print("log", welcome_text)


def init_recipes():
    """Store information related to each supported AutoPkg recipe type.

    Returns:
        A tuple of dicts that describe all the AutoPkg recipe types we know about.
    """

    recipes = (
        {
            "name": "download",
            "description": "Downloads an app in whatever format the developer "
            "provides."
        },
        {
            "name": "munki",
            "description": "Imports into your Munki repository."
        },
        {
            "name": "pkg",
            "description": "Creates a standard pkg installer file."
        },
        {
            "name": "install",
            "description": "Installs the app on the computer running AutoPkg."
        },
        {
            "name": "jss",
            "description": "Imports into your Casper JSS and creates "
            "necessary groups, policies, etc."
        },
        {
            "name": "absolute",
            "description": "Imports into your Absolute Manage server."
        },
        {
            "name": "sccm",
            "description": "Creates a cmmac package for deploying via "
            "Microsoft SCCM."
        },
        {
            "name": "ds",
            "description": "Imports into your DeployStudio Packages folder."
        }
    )

    # Set default values for all recipe types.
    for recipe in recipes:
        recipe["preferred"] = True
        recipe["existing"] = False
        recipe["buildable"] = False
        recipe["selected"] = True
        recipe["icon_path"] = ""
        # TODO(Elliot):  Move the default keys to the generation function.
        recipe["keys"] = {
            "Identifier": "",
            "MinimumVersion": "0.5.0",
            "Input": {},
            "Process": [],
            "Comment": "Generated by Recipe Robot v%s "
                       "(https://github.com/homebysix/recipe-robot)" % version
        }

    return recipes


def init_prefs(prefs, recipes, args):
    """Read Recipe Robot preferences in the following priority order:
        0. If --config argument is specified, skip to step 4.
        1. If a setting is defined in a command line argument, use it.
        2. If a setting is defined in an input plist, use it.
        3. If neither of the above, and a preferences plist exists, use it.
        4. If none of the above or if --config is specified, prompt user
           for each setting, then save to a preferences plist that will be
           used in step 3 next time.

    Args:
        prefs: TODO
        recipes: TODO
        args: TODO

    Returns:
        prefs: TODO
    """

    prefs = {
        "input_path": "",
        "identifier_prefix": "",
        "recipe_types": [],
        "output_dir": "",
    }
    global verbose_mode
    global prefs_file

    # If --config is specified, build preferences from scratch.
    if args.config is True:
        robo_print("log", "Showing configuration options...")
        prefs = build_prefs(prefs, recipes, args)

    # If an input plist is specified, use that for one-time preferences.
    elif args.input_path.endswith(".plist"):
        prefs_file = args.input_path

    # WIP

    # If prefs file exists, try to read from it.
    if os.path.isfile(prefs_file):
        try:
            prefs = FoundationPlist.readPlist(prefs_file)
            for recipe in recipes:
                # Load preferred recipe types.
                if recipe["name"] in prefs["recipe_types"]:
                    recipe["preferred"] = True
                else:
                    recipe["preferred"] = False
        except Exception:
            robo_print("warning",
                       "There was a problem opening the prefs file at %s. "
                       "Building new preferences." % prefs_file)
            prefs = build_prefs(prefs, recipes, args)

    else:
        robo_print("warning",
                   "No prefs file found. Building new preferences...")
        prefs = build_prefs(prefs, recipes, args)

    # Record last version number.
    prefs["LastRecipeRobotVersion"] = version

    # Write preferences to plist.
    FoundationPlist.writePlist(prefs, prefs_file)

    return prefs


def build_prefs(prefs, recipes, args):
    """Prompt user for preferences, then save them back to the plist.

    Args:
        prefs: TODO
        recipes: TODO
        args: TODO

    Returns:
        prefs: TODO
    """

    # Start recipe count at zero.
    prefs["RecipeCreateCount"] = 0

    # Prompt for and save recipe identifier prefix.
    prefs["RecipeIdentifierPrefix"] = "com.github.homebysix"
    robo_print("log", "\nRecipe identifier prefix")
    robo_print("log", "This is your default identifier, in reverse-domain notation.\n")
    choice = raw_input(
        "[%s]: " % prefs["RecipeIdentifierPrefix"])
    if choice != "":
        prefs["RecipeIdentifierPrefix"] = str(choice).rstrip(". ")

    # Prompt for recipe creation location.
    prefs["RecipeCreateLocation"] = "~/Library/AutoPkg/RecipeOverrides"
    robo_print("log", "\nLocation to save new recipes")
    robo_print("log", "This is where on disk your newly created recipes will be saved.\n")
    choice = raw_input(
        "[%s]: " % prefs["RecipeCreateLocation"])
    if choice != "":
        prefs["RecipeCreateLocation"] = str(choice).rstrip("/ ")

    # Prompt to set recipe types on/off as desired.
    prefs["RecipeTypes"] = []
    robo_print("log", "\nPreferred recipe types")
    robo_print("log", "Choose which recipe types will be offered to you by default.\n")
    # TODO(Elliot): Make this interactive while retaining scrollback.
    # Maybe with curses module?
    while True:
        i = 0
        for recipe in recipes:
            if recipe["preferred"] is False:
                indicator = " "
            else:
                indicator = "*"
            robo_print("log", "  [%s] %s. %s - %s" %
                       (indicator, i, recipe["name"], recipe["description"]))
            i += 1
        robo_print("log", "      A. Enable all recipe types.")
        robo_print("log", "      D. Disable all recipe types.")
        robo_print("log", "      Q. Quit without saving changes.")
        robo_print("log", "      S. Save changes and proceed.")
        choice = raw_input(
            "\nType a number to toggle the corresponding recipe "
            "type between ON [*] and OFF [ ].\nWhen you're satisfied "
            "with your choices, type an \"S\" to save and proceed: ")
        if choice.upper() == "S":
            break
        elif choice.upper() == "A":
            for recipe in recipes:
                recipe["preferred"] = True
        elif choice.upper() == "D":
            for recipe in recipes:
                recipe["preferred"] = False
        elif choice.upper() == "Q":
            sys.exit(0)
        else:
            try:
                if recipes[int(choice)]["preferred"] is False:
                    recipes[int(choice)]["preferred"] = True
                else:
                    recipes[int(choice)]["preferred"] = False
            except Exception:
                robo_print("warning", "%s is not a valid option. Please try again.\n" % choice)

    # Set "preferred" status of each recipe type according to preferences.
    for recipe in recipes:
        if recipe["preferred"] is True:
            prefs["RecipeTypes"].append(recipe["name"])

    return prefs


def get_sparkle_download_format(sparkle_url):
    """Parse a Sparkle feed URL and return the type of download it produces.

    Args:
        sparkle_url: TODO

    Returns:
        String containing the format of the Sparkle-provided download.
    """

    # TODO(Elliot): There's got to be a better way than curl.
    cmd = "curl -s %s | awk -F 'url=\"|\"' '/enclosure url/{print $2}' | head -1" % sparkle_url
    exitcode, out, err = get_exitcode_stdout_stderr(cmd)
    if exitcode == 0:
        for this_format in all_supported_formats:
            if out.endswith(this_format):
                return this_format


def increment_recipe_count(prefs):
    """Add 1 to the cumulative count of recipes created by Recipe Robot.

    Args:
        prefs: TODO
    """

    prefs["RecipeCreateCount"] += 1
    FoundationPlist.writePlist(prefs, prefs_file)


def get_app_description(app_name):
    """Use an app's name to generate a description from MacUpdate.com.

    Args:
        app_name: TODO

    Returns:
        description: A string containing a description of the app.
    """

    # Start with an empty string. (If it remains empty, the parent function
    # will know that no description was available.)
    description = ""

    # This is the HTML immediately preceding the description text on the
    # MacUpdate search results page.
    description_marker = "-shortdescrip\">"

    cmd = "curl -s \"http://www.macupdate.com/find/mac/\"" + app_name
    exitcode, out, err = get_exitcode_stdout_stderr(cmd)

    # For each line in the resulting text, look for the description marker.
    html = out.split("\n")
    if exitcode == 0:
        for line in html:
            if description_marker in line:
                # Trim the HTML from the beginning of the line.
                start = line.find(description_marker) + len(description_marker)
                # Trim the HTML from the end of the line.
                description = line[start:].rstrip("</span>")
                # If we found a description, no need to process further lines.
                break
    else:
        robo_print("warning", err)

    return description


def create_existing_recipe_list(app_name, recipes):
    """Use autopkg search results to build existing recipe list.

    Args:
        app_name: TODO
        recipes: TODO
    """

    # TODO(Elliot): Suggest users create GitHub API token to prevent limiting.

    recipe_searches = []
    recipe_searches.append(app_name)

    app_name_no_space = "".join(app_name.split())
    if app_name_no_space != app_name:
        recipe_searches.append(app_name_no_space)

    app_name_no_symbol = re.sub(r'[^\w]', '', app_name)
    if app_name_no_symbol != app_name and app_name_no_symbol != app_name_no_space:
        recipe_searches.append(app_name_no_symbol)

    for this_search in recipe_searches:
        robo_print("log", "Searching for existing AutoPkg recipes for %s..." % this_search)
        cmd = "/usr/local/bin/autopkg search -p \"%s\"" % this_search
        exitcode, out, err = get_exitcode_stdout_stderr(cmd)
        if exitcode == 0:
            # TODO(Elliot): There's probably a more efficient way to do this.
            # For each recipe type, see if it exists in the search results.
            for recipe in recipes:
                recipe_name = "%s.%s.recipe" % (this_search, recipe["name"])
                for line in out.split("\n"):
                    if recipe_name in line:
                        # Set to False by default. If found, set to True.
                        recipe["existing"] = True
                        robo_print("log", "Found existing %s." % recipe_name)
        else:
            robo_print("error", err)


def create_buildable_recipe_list(app_name, recipes, args):
    """Add any preferred recipe types that don't already exist to the buildable
    list.

    Args:
        app_name: TODO
        recipes: TODO
        args: TODO
    """

    for recipe in recipes:
        if args.include_existing is False:
            if recipe["preferred"] is True and recipe["existing"] is False:
                recipe["buildable"] = True
        else:
            if recipe["preferred"] is True:
                recipe["buildable"] = True


# TODO(Shea): Let's have a think about how we're handling input in the
# functions below. In addition to external input (the arguments passed
# when the script is run) we may want to handle internal input too (from
# one recipe type to another).

def handle_github_url_input(input_path, recipes, args, prefs):
    """Process a GitHub URL, gathering required information to create a
    recipe.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """
    pass


def handle_sourceforge_url_input(input_path, recipes, args, prefs):
    """Process a SourceForge URL, gathering required information to create a
    recipe.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """
    pass


def handle_download_url_input(input_path, recipes, args, prefs):
    """Process a direct download URL, gathering required information to
    create a recipe.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """
    pass


def handle_app_input(input_path, recipes, args, prefs):
    """Process an app, gathering required information to create a recipe.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """

    # Create variables for every piece of information we might need to create
    # any sort of AutoPkg recipe. Then populate those variables with the info.

    app_name = ""
    robo_print("verbose", "Validating app...")
    try:
        info_plist = FoundationPlist.readPlist(input_path + "/Contents/Info.plist")
    except Exception:
        robo_print("error", "This doesn't look like a valid app to me.")
    if app_name == "":  # Will always be true at this point.
        robo_print("verbose", "Determining app's name from CFBundleName...")
        try:
            app_name = info_plist["CFBundleName"]
        except KeyError:
            robo_print("warning", "This app doesn't have a CFBundleName. That's OK, we'll keep trying.")
    if app_name == "":
        robo_print("verbose", "Determining app's name from CFBundleExecutable...")
        try:
            app_name = info_plist["CFBundleExecutable"]
        except KeyError:
            robo_print("warning", "This app doesn't have a CFBundleExecutable. The plot thickens.")
    if app_name == "":
        robo_print("verbose", "Determining app's name from input path...")
        app_name = os.path.basename(input_path)[:-4]
    robo_print("verbose", "    App name is: %s" % app_name)

    # Search for existing recipes that match the app's name.
    if args.include_existing is not True:
        create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes, args)

    # Attempt to determine how to download this app.
    sparkle_feed = ""
    github_repo = ""
    sourceforge_id = ""
    download_format = ""
    robo_print("verbose", "Checking for a Sparkle feed in SUFeedURL...")
    try:
        sparkle_feed = info_plist["SUFeedURL"]
        download_format = get_sparkle_download_format(sparkle_feed)
    except Exception:
        robo_print("warning", "No SUFeedURL found in this app's Info.plist.")
    if sparkle_feed == "":
        robo_print("log", "Checking for a Sparkle feed in SUOriginalFeedURL...")
        try:
            sparkle_feed = info_plist["SUOriginalFeedURL"]
            download_format = get_sparkle_download_format(sparkle_feed)
        except Exception:
            robo_print("warning", "No SUOriginalFeedURL found in this app's Info.plist.")
    if sparkle_feed == "":
        robo_print("error", "Sorry, this app doesn't have a Sparkle feed.")
        # TODO(Elliot): Make this error into a warning once we can support
        # GitHub and SourceForge searching. Until then, Sparkle or bust.
    else:
        robo_print("verbose", "    Sparkle feed is: %s" % sparkle_feed)
    if sparkle_feed == "":
        # TODO(Elliot): search_sourceforge_and_github(app_name)
        # if github release
            # github_repo = ""
        # if sourceforge release
            # sourceforge_id = ""
        # TODO(Elliot): Find out what format the GH/SF feed downloads in.
        pass

    # Attempt to determine minimum compatible OS X version.
    min_sys_vers = ""
    robo_print("verbose", "Checking for minimum OS version requirements...")
    try:
        min_sys_vers = info_plist["LSMinimumSystemVersion"]
        robo_print("verbose", "    Minimum OS version: %s" % min_sys_vers)
    except Exception:
        robo_print("warning", "No LSMinimumSystemVersion found.")

    # Determine path to the app's icon.
    icon_path = ""
    robo_print("verbose", "Looking for app icon...")
    try:
        icon_path = "%s/Contents/Resources/%s" % (
            input_path, info_plist["CFBundleIconFile"])
        robo_print("verbose", "    Icon found: %s" % icon_path)
    except Exception:
        robo_print("warning", "No CFBundleIconFile found in this app's Info.plist.")

    # Determine the bundle identifier of the app.
    bundle_id = ""
    robo_print("verbose", "Getting bundle identifier...")
    try:
        bundle_id = info_plist["CFBundleIdentifier"]
        robo_print("verbose", "    Bundle ID: %s" % bundle_id)
    except Exception:
        robo_print("warning", "No CFBundleIdentifier found in this app's Info.plist.")

    # Attempt to get a description of the app from MacUpdate.com.
    description = ""
    robo_print("verbose", "Getting app description from MacUpdate...")
    try:
        description = get_app_description(app_name)
        robo_print("verbose", "    Description: %s" % description)
    except Exception:
        pass
    if description == "":
        robo_print("warning", "Could not get app description.")

    # Attempt to determine code signing verification/requirements.
    cmd = "codesign --display -r- \"%s\"" % (input_path)
    exitcode, out, err = get_exitcode_stdout_stderr(cmd)
    if exitcode == 0:
        code_signed = True
        code_sign_reqs = ""

        # Determine code signing requirements.
        marker = "designated => "
        for line in out.split("\n"):
            if line.startswith(marker):
                code_sign_reqs = line[len(marker):]

    else:
        code_signed = False

    # TODO(Elliot): Collect other information as required to build recipes.
    #    - Use bundle identifier to locate related helper apps on disk?
    #    - App category... maybe prompt for that if JSS recipe is selected.
    #    - Does the CFBundleShortVersionString provide a usable version number,
    #      or do we need to use CFBundleVersionString instead? (Will be
    #      relevant when producing JSS recipes that might require ext attrib.)

    # Send the information we discovered to the recipe keys.
    for recipe in recipes:
        recipe["keys"]["Input"]["NAME"] = app_name

        # Set the identifier of the recipe.
        recipe["keys"]["Identifier"] = "%s.%s.%s" % (
            prefs["RecipeIdentifierPrefix"], recipe["name"], app_name)

        if recipe["buildable"] is True:

            if recipe["name"] == "download":
                recipe["keys"]["Description"] = "Downloads the latest version of %s." % recipe[
                    "keys"]["Input"]["NAME"]
                if sparkle_feed != "":
                    # Example: Cyberduck.download
                    recipe["keys"]["Input"][
                        "SPARKLE_FEED_URL"] = sparkle_feed
                    recipe["keys"]["Process"].append({
                        "Processor": "SparkleUpdateInfoProvider",
                        "Arguments": {
                            "appcast_url": "%SPARKLE_FEED_URL%"
                        }
                    })
                elif github_repo != "":
                    # Example: AutoCaperNBI.download
                    recipe["keys"]["Process"].append({
                        "Processor": "GitHubReleasesInfoProvider",
                        "Arguments": {
                            "github_repo": github_repo
                        }
                    })
                elif sourceforge_id != "":
                    # Example: GrandPerspective.download
                    recipe["keys"]["Input"][
                        "SOURCEFORGE_FILE_PATTERN"] = "%s-[0-9_\.]*\.%s" % (app_name, download_format),
                    recipe["keys"]["Input"][
                        "SOURCEFORGE_PROJECT_ID"] = sourceforge_id
                # end if
                recipe["keys"]["Process"].append({
                    "Processor": "URLDownloader",
                    "Arguments": {
                        "filename": "%%NAME%%-%%version%%.%s" % download_format
                    }
                })
                recipe["keys"]["Process"].append({
                    "Processor": "EndOfCheckPhase"
                })
                if code_signed is True:
                    if code_sign_reqs != "":
                        code_sign_args = {
                            "input_path": "%%pathname%%/%s.app" % app_name,
                            "requirement": code_sign_reqs
                        }
                    else:
                        code_sign_args = {
                            "input_path": "%%pathname%%/%s.app" % app_name
                        }

                    if download_format in supported_image_formats:
                        recipe["keys"]["Process"].append({
                            "Processor": "CodeSignatureVerifier",
                            "Arguments": code_sign_args
                        })
                    elif download_format in supported_install_formats:
                        # TODO(Elliot):  Check for code signing on pkg download?
                        pass
                    elif download_format in supported_archive_formats:
                        recipe["keys"]["Process"].append({
                            "Processor": "Unarchiver",
                            "Arguments": {
                                "archive_path": "%pathname%",
                                "destination_path": "%RECIPE_CACHE_DIR%/%NAME%",
                                "purge_destination": True
                            }
                        })
                        recipe["keys"]["Process"].append({
                            "Processor": "CodeSignatureVerifier",
                            "Arguments": code_sign_args
                        })
                        recipe["keys"]["Process"].append({
                            "Processor": "PathDeleter",
                            "Arguments": {
                                "path_list": [
                                    "%RECIPE_CACHE_DIR%/%NAME%"
                                ]
                            }
                        })

            if recipe["name"] == "munki":
                # Example: Firefox.munki
                recipe["keys"]["Description"] = "Imports the latest version of %s into Munki." % recipe[
                    "keys"]["Input"]["NAME"]
                recipe["keys"]["ParentRecipe"] = "%s.download.%s" % (prefs["RecipeIdentifierPrefix"], recipe[
                    "keys"]["Input"]["NAME"])
                if icon_path != "":
                    png_path = "%s/%s.png" % (
                        prefs["RecipeCreateLocation"], app_name)
                    extract_app_icon(recipe["icon_path"], png_path)
                # TODO(Elliot): Review inline comments below and adjust.
                recipe["keys"]["Input"][
                    "MUNKI_REPO_SUBDIR"] = "apps/%s" % app_name
                recipe["keys"]["Input"]["pkginfo"] = {
                    "catalogs": ["testing"],
                    "description": description,
                    "display_name": app_name,
                    "icon_name": "%s.png" % app_name,
                    "name": app_name,
                    "unattended_install": True  # Always?
                }
                recipe["keys"]["Process"].append({
                    "Processor": "MunkiImporter",
                    "Arguments": {
                        # TODO(Elliot): Bug is setting download_format to None.
                        "pkg_path": "%RECIPE_CACHE_DIR%/%NAME%." + str(download_format),
                        "repo_subdirectory": "%MUNKI_REPO_SUBDIR%"
                    }
                })

            if recipe["name"] == "pkg":
                recipe["keys"]["Description"] = "Downloads the latest version of %s and creates an installer package." % recipe[
                    "keys"]["Input"]["NAME"]
                recipe["keys"]["ParentRecipe"] = "%s.download.%s" % (prefs["RecipeIdentifierPrefix"], recipe[
                    "keys"]["Input"]["NAME"])
                if bundle_id != "":
                    recipe["keys"]["Input"]["PKG_ID"] = bundle_id
                recipe["keys"]["Process"].append({
                    "Processor": "PkgRootCreator",
                    "Arguments": {
                        "pkgroot": "%RECIPE_CACHE_DIR%/%NAME%",
                        "pkgdirs": {
                            "Applications": "0775"
                        }
                    }
                })
                if download_format in supported_image_formats:
                    # Example: AutoPkgr.pkg
                    recipe["keys"]["Process"].append({
                        "Processor": "AppDmgVersioner",
                        "Arguments": {
                            "dmg_path": "%pathname%"
                        }
                    })
                    recipe["keys"]["Process"].append({
                        "Processor": "Copier",
                        "Arguments": {
                            "source_path": "%pathname%/%NAME%.app",
                            "destination_path": "%pkgroot%/Applications/%NAME%.app"
                        }
                    })
                elif download_format in supported_install_formats:
                    # TODO(Elliot): Code sign verify for pkg?
                    pass
                elif download_format in supported_archive_formats:
                    # Example: AppZapper.pkg
                    recipe["keys"]["Process"].append({
                        "Processor": "Unarchiver",
                        "Arguments": {
                            "archive_path": "%pathname%",
                            "destination_path": "%RECIPE_CACHE_DIR%/%NAME%/Applications"
                        }
                    })
                    recipe["keys"]["Process"].append({
                        "Processor": "Versioner",
                        "Arguments": {
                            "input_plist_path": "%RECIPE_CACHE_DIR%/%NAME%/Applications/%NAME%.app/Contents/Info.plist",
                            "plist_version_key": "CFBundleShortVersionString"
                        }
                    })
                # end if
                recipe["keys"]["Process"].append({
                    "Processor": "PkgCreator",
                    "Arguments": {
                        "pkg_request": {
                            "pkgname": "%NAME%-%version%",
                            "version": "%version%",
                            "id": "%PKG_ID%",
                            "options": "purge_ds_store",
                            "chown": [{
                                "path": "Applications",
                                "user": "root",
                                "group": "admin"
                            }]
                        }
                    }
                })

            if recipe["name"] == "install":
                recipe["keys"]["Description"] = "Installs the latest version of %s." % recipe[
                    "keys"]["Input"]["NAME"]
                recipe["keys"]["ParentRecipe"] = "%s.pkg.%s" % (prefs["RecipeIdentifierPrefix"], recipe[
                    "keys"]["Input"]["NAME"])

            if recipe["name"] == "jss":
                recipe["keys"]["Description"] = "Imports the latest version of %s into your JSS." % recipe[
                    "keys"]["Input"]["NAME"]
                recipe["keys"]["ParentRecipe"] = "%s.pkg.%s" % (prefs["RecipeIdentifierPrefix"], recipe[
                    "keys"]["Input"]["NAME"])
                recipe["keys"]["Input"]["category"] = "None"
                recipe["keys"]["Input"]["policy_category"] = "Testing"
                recipe["keys"]["Input"][
                    "policy_template"] = "PolicyTemplate.xml"
                recipe["keys"]["Input"]["groups"] = []
                recipe["keys"]["Input"][
                    "GROUP_TEMPLATE"] = "SmartGroupTemplate.xml"
                if icon_path != "":
                    png_path = "%s/%s.png" % (
                        prefs["RecipeCreateLocation"], app_name)
                    extract_app_icon(recipe["icon_path"], png_path)
                recipe["keys"]["Input"]["prod_name"] = app_name
                if icon_path != "":
                    recipe["keys"]["Input"][
                        "self_service_icon"] = app_name + ".png"
                recipe["keys"]["Input"][
                    "self_service_description"] = description
                recipe["keys"]["Input"][
                    "GROUP_NAME"] = app_name + "-update-smart"

            if recipe["name"] == "absolute":
                recipe["keys"]["Description"] = "Imports the latest version of %s into Absolute Manage." % recipe[
                    "keys"]["Input"]["NAME"]
                recipe["keys"]["ParentRecipe"] = "%s.pkg.%s" % (prefs["RecipeIdentifierPrefix"], recipe[
                    "keys"]["Input"]["NAME"])

            if recipe["name"] == "sccm":
                recipe["keys"]["Description"] = "Downloads the latest version of %s and creates a cmmac package for deploying via Microsoft SCCM." % recipe[
                    "keys"]["Input"]["NAME"]
                recipe["keys"]["ParentRecipe"] = "%s.pkg.%s" % (prefs["RecipeIdentifierPrefix"], recipe[
                    "keys"]["Input"]["NAME"])

            if recipe["name"] == "ds":
                recipe["keys"]["Description"] = "Imports the latest version of %s into DeployStudio." % recipe[
                    "keys"]["Input"]["NAME"]
                recipe["keys"]["ParentRecipe"] = "%s.download.%s" % (prefs["RecipeIdentifierPrefix"], recipe[
                    "keys"]["Input"]["NAME"])


def handle_download_recipe_input(input_path, recipes, args, prefs):
    """Process a download recipe, gathering information useful for building
    other types of recipes.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """

    # Read the recipe as a plist.
    input_recipe = FoundationPlist.readPlist(input_path)

    robo_print("verbose", "Determining app's name from NAME input key...")
    app_name = input_recipe["Input"]["NAME"]
    robo_print("verbose", "    App name is: %s" % app_name)

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes, args)

    # Get the download file format.
    # TODO(Elliot): Parse the recipe properly. Don't use grep.
    robo_print("verbose", "Determining download format...")
    parsed_download_format = ""
    for download_format in all_supported_formats:
        cmd = "grep '.%s</string>' '%s'" % (download_format, input_path)
        exitcode, out, err = get_exitcode_stdout_stderr(cmd)
        if exitcode == 0:
            robo_print("verbose", "    Download format: %s." % download_format)
            parsed_download_format = download_format
            break

    # Send the information we discovered to the recipe keys.
    # This information is type-specific. Universal keys like Identifier are
    # set when the recipe is generated.
    for recipe in recipes:
        recipe["keys"]["Input"]["NAME"] = app_name
        recipe["keys"]["ParentRecipe"] = input_recipe["Identifier"]
        if recipe["buildable"] is True:

            if recipe["name"] == "munki":
                pass

            if recipe["name"] == "pkg":
                if parsed_download_format in supported_image_formats:
                    # Example: GoogleChrome.pkg
                    recipe["Process"].append({
                        "Processor": "AppDmgVersioner",
                        "Arguments": {
                            "dmg_path": "%pathname%"
                        }
                    })
                    recipe["keys"]["Process"].append({
                        "Processor": "PkgRootCreator",
                        "Arguments": {
                            "pkgroot": "%RECIPE_CACHE_DIR%/%NAME%",
                            "pkgdirs": {
                                "Applications": "0775"
                            }
                        }
                    })
                    recipe["keys"]["Process"].append({
                        "Processor": "Copier",
                        "Arguments": {
                            "source_path": "%pathname%/%app_name%",
                            "destination_path": "%pkgroot%/Applications/%app_name%"
                        }
                    })
                    recipe["keys"]["Process"].append({
                        "Processor": "PkgCreator",
                        "Arguments": {
                            "pkg_request": {
                                "pkgname": "%NAME%-%version%",
                                "version": "%version%",
                                # TODO(Elliot): How to determine bundle ID
                                # from the .dmg?
                                "id": "%bundleid%",
                                "options": "purge_ds_store",
                                "chown": ({
                                    "path": "Applications",
                                    "user": "root",
                                    "group": "admin"
                                })
                            }
                        }
                    })
                elif parsed_download_format in supported_archive_formats:
                    # Example: TheUnarchiver.pkg
                    recipe["Process"].append({
                        "Processor": "PkgRootCreator",
                        "Arguments": {
                            "pkgroot": "%RECIPE_CACHE_DIR%/%NAME%",
                            "pkgdirs": {
                                "Applications": "0775"
                            }
                        }
                    })
                    recipe["keys"]["Process"].append({
                        "Processor": "Unarchiver",
                        "Arguments": {
                            "archive_path": "%pathname%",
                            "destination_path": "%pkgroot%/Applications",
                            "purge_destination": True
                        }
                    })
                    recipe["keys"]["Process"].append({
                        "Processor": "Versioner",
                        "Arguments": {
                            "input_plist_path": "%pkgroot%/Applications/The Unarchiver.app/Contents/Info.plist",
                            "plist_version_key": "CFBundleShortVersionString"
                        }
                    })
                    recipe["keys"]["Process"].append({
                        "Processor": "PkgCreator",
                        "Arguments": {
                            "pkg_request": {
                                "pkgname": "%NAME%-%version%",
                                "version": "%version%",
                                # TODO(Elliot): How to determine bundle ID
                                # from the .zip? Get it from Info.plist
                                # above?
                                "id": "%bundleid%",
                                "options": "purge_ds_store",
                                "chown": ({
                                    "path": "Applications",
                                    "user": "root",
                                    "group": "admin"
                                })
                            }
                        }
                    })
                elif parsed_download_format in supported_install_formats:
                    # TODO(Elliot): Do we want to create download recipes for
                    # .pkg downloads, or skip right to the pkg recipe? I vote
                    # for making a download recipe, since the download format
                    # may possibly change someday.
                    pass
                else:
                    # TODO(Elliot): Construct keys for remaining supported
                    # download formats.
                    pass

            if recipe["name"] == "install":
                pass

            if recipe["name"] == "jss":
                pass

            if recipe["name"] == "absolute":
                pass

            if recipe["name"] == "sccm":
                pass

            if recipe["name"] == "ds":
                pass


def handle_munki_recipe_input(input_path, recipes, args, prefs):
    """Process a munki recipe, gathering information useful for building other
    types of recipes.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """

    # Determine whether there's already a download Parent recipe.
    # If not, add it to the list of offered recipe formats.

    # Read the recipe as a plist.
    input_recipe = FoundationPlist.readPlist(input_path)

    robo_print("verbose", "Determining app's name from NAME input key...")
    app_name = input_recipe["Input"]["NAME"]
    robo_print("verbose", "    App name is: %s" % app_name)

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes, args)

    # If this munki recipe both downloads and imports the app, we
    # should offer to build a discrete download recipe with only
    # the appropriate sections of the munki recipe.

    # Offer to build pkg, jss, etc.

    # TODO(Elliot): Think about whether we want to dig into OS requirements,
    # blocking applications, etc when building munki recipes. I vote
    # yes, but it's probably not going to be easy.

    # Send the information we discovered to the recipe keys.
    for recipe in recipes:
        recipe["keys"]["Input"]["NAME"] = app_name
        recipe["keys"]["ParentRecipe"] = input_recipe["Identifier"]
        if recipe["buildable"] is True:

            if recipe["name"] == "download":
                pass

            if recipe["name"] == "pkg":
                pass

            if recipe["name"] == "install":
                pass

            if recipe["name"] == "jss":
                pass

            if recipe["name"] == "absolute":
                pass

            if recipe["name"] == "sccm":
                pass

            if recipe["name"] == "ds":
                pass


def handle_pkg_recipe_input(input_path, recipes, args, prefs):
    """Process a pkg recipe, gathering information useful for building other
    types of recipes.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """

    # Read the recipe as a plist.
    input_recipe = FoundationPlist.readPlist(input_path)

    robo_print("verbose", "Determining app's name from NAME input key...")
    app_name = input_recipe["Input"]["NAME"]
    robo_print("verbose", "    App name is: %s" % app_name)

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes, args)

    # Check to see whether the recipe has a download recipe as its parent. If
    # not, offer to build a discrete download recipe.

    # Send the information we discovered to the recipe keys.
    for recipe in recipes:
        recipe["keys"]["Input"]["NAME"] = app_name
        recipe["keys"]["ParentRecipe"] = input_recipe["Identifier"]
        if recipe["buildable"] is True:

            if recipe["name"] == "download":
                pass

            if recipe["name"] == "munki":
                pass

            if recipe["name"] == "install":
                pass

            if recipe["name"] == "jss":
                pass

            if recipe["name"] == "absolute":
                pass

            if recipe["name"] == "sccm":
                pass

            if recipe["name"] == "ds":
                pass


def handle_install_recipe_input(input_path, recipes, args, prefs):
    """Process an install recipe, gathering information useful for building
    other types of recipes.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """

    # Read the recipe as a plist.
    input_recipe = FoundationPlist.readPlist(input_path)

    robo_print("verbose", "Determining app's name from NAME input key...")
    app_name = input_recipe["Input"]["NAME"]
    robo_print("verbose", "    App name is: %s" % app_name)

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes, args)

    # Check to see whether the recipe has a download and/or pkg
    # recipe as its parent. If not, offer to build a discrete
    # download and/or pkg recipe.

    # Send the information we discovered to the recipe keys.
    for recipe in recipes:
        recipe["keys"]["Input"]["NAME"] = app_name
        recipe["keys"]["ParentRecipe"] = input_recipe["Identifier"]
        if recipe["buildable"] is True:

            if recipe["name"] == "download":
                pass

            if recipe["name"] == "munki":
                pass

            if recipe["name"] == "pkg":
                pass

            if recipe["name"] == "jss":
                pass

            if recipe["name"] == "absolute":
                pass

            if recipe["name"] == "sccm":
                pass

            if recipe["name"] == "ds":
                pass


def handle_jss_recipe_input(input_path, recipes, args, prefs):
    """Process a jss recipe, gathering information useful for building other
    types of recipes.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """

    # Read the recipe as a plist.
    input_recipe = FoundationPlist.readPlist(input_path)

    robo_print("verbose", "Determining app's name from NAME input key...")
    app_name = input_recipe["Input"]["NAME"]
    robo_print("verbose", "    App name is: %s" % app_name)

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes, args)

    # Check to see whether the recipe has a download and/or pkg
    # recipe as its parent. If not, offer to build a discrete
    # download and/or pkg recipe.

    # Send the information we discovered to the recipe keys.
    for recipe in recipes:
        recipe["keys"]["Input"]["NAME"] = app_name
        recipe["keys"]["ParentRecipe"] = input_recipe["Identifier"]
        if recipe["buildable"] is True:

            if recipe["name"] == "download":
                pass

            if recipe["name"] == "munki":
                pass

            if recipe["name"] == "pkg":
                pass

            if recipe["name"] == "install":
                pass

            if recipe["name"] == "absolute":
                pass

            if recipe["name"] == "sccm":
                pass

            if recipe["name"] == "ds":
                pass


def handle_absolute_recipe_input(input_path, recipes, args, prefs):
    """Process an absolute recipe, gathering information useful for building
    other types of recipes.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """

    # Read the recipe as a plist.
    input_recipe = FoundationPlist.readPlist(input_path)

    robo_print("verbose", "Determining app's name from NAME input key...")
    app_name = input_recipe["Input"]["NAME"]
    robo_print("verbose", "    App name is: %s" % app_name)

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes, args)

    # Check to see whether the recipe has a download and/or pkg
    # recipe as its parent. If not, offer to build a discrete
    # download and/or pkg recipe.

    # Send the information we discovered to the recipe keys.
    for recipe in recipes:
        recipe["keys"]["Input"]["NAME"] = app_name
        recipe["keys"]["ParentRecipe"] = input_recipe["Identifier"]
        if recipe["buildable"] is True:

            if recipe["name"] == "download":
                pass

            if recipe["name"] == "munki":
                pass

            if recipe["name"] == "pkg":
                pass

            if recipe["name"] == "install":
                pass

            if recipe["name"] == "jss":
                pass

            if recipe["name"] == "sccm":
                pass

            if recipe["name"] == "ds":
                pass


def handle_sccm_recipe_input(input_path, recipes, args, prefs):
    """Process a sccm recipe, gathering information useful for building other
    types of recipes.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """

    # Read the recipe as a plist.
    input_recipe = FoundationPlist.readPlist(input_path)

    robo_print("verbose", "Determining app's name from NAME input key...")
    app_name = input_recipe["Input"]["NAME"]
    robo_print("verbose", "    App name is: %s" % app_name)

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes, args)

    # Check to see whether the recipe has a download and/or pkg
    # recipe as its parent. If not, offer to build a discrete
    # download and/or pkg recipe.

    # Send the information we discovered to the recipe keys.
    for recipe in recipes:
        recipe["keys"]["Input"]["NAME"] = app_name
        recipe["keys"]["ParentRecipe"] = input_recipe["Identifier"]
        if recipe["buildable"] is True:

            if recipe["name"] == "download":
                pass

            if recipe["name"] == "munki":
                pass

            if recipe["name"] == "pkg":
                pass

            if recipe["name"] == "install":
                pass

            if recipe["name"] == "jss":
                pass

            if recipe["name"] == "absolute":
                pass

            if recipe["name"] == "ds":
                pass


def handle_ds_recipe_input(input_path, recipes, args, prefs):
    """Process a ds recipe, gathering information useful for building other
    types of recipes.

    Args:
        input_path: TODO
        recipes: TODO
        args: TODO
        prefs: TODO
    """

    # Read the recipe as a plist.
    input_recipe = FoundationPlist.readPlist(input_path)

    robo_print("verbose", "Determining app's name from NAME input key...")
    app_name = input_recipe["Input"]["NAME"]
    robo_print("verbose", "    App name is: %s" % app_name)

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes, args)

    # Check to see whether the recipe has a download and/or pkg
    # recipe as its parent. If not, offer to build a discrete
    # download and/or pkg recipe.

    # Send the information we discovered to the recipe keys.
    for recipe in recipes:
        recipe["keys"]["Input"]["NAME"] = app_name
        recipe["keys"]["ParentRecipe"] = input_recipe["Identifier"]
        if recipe["buildable"] is True:

            if recipe["name"] == "download":
                pass

            if recipe["name"] == "munki":
                pass

            if recipe["name"] == "pkg":
                pass

            if recipe["name"] == "install":
                pass

            if recipe["name"] == "jss":
                pass

            if recipe["name"] == "absolute":
                pass

            if recipe["name"] == "sccm":
                pass


def search_sourceforge_and_github(app_name):
    """For apps that do not have a Sparkle feed, try to locate their project
    information on either SourceForge or GitHub so that the corresponding
    URL provider processors can be used to generate a recipe.

    Args:
        app_name: TODO
    """

    # TODO(Shea): Search on SourceForge for the project.
    #     Search URL: http://sourceforge.net/directory/developmentstatus:production/os:mac/?q=_____
    #     If found, pass the project ID back to the recipe generator.
    #     To get ID: https://gist.github.com/homebysix/9640c6a6eecff82d3b16
    # TODO(Shea): Search on GitHub for the project.
    #     Search URL: https://github.com/search?utf8=✓&type=Repositories&ref=searchresults&q=_____
    #     If found, pass the repo string back to the recipe generator.


def select_recipes_to_generate(recipes):
    """Display menu that allows user to select which recipes to create.

    Args:
        recipes: TODO
    """

    buildable_count = 0
    for recipe in recipes:
        if recipe["buildable"] is True:
            buildable_count += 1

    if buildable_count < 1:
        robo_print("error", "Sorry, there are no recipe types to generate.")

    robo_print("log", "\nPlease select which recipes you'd like to create:\n")

    # TODO(Elliot): Make this interactive while retaining scrollback.
    # Maybe with curses module?
    while True:
        i = 0
        for recipe in recipes:
            indicator = " "
            if (recipe["preferred"] is True and recipe["buildable"] is True):
                if recipe["selected"] is True:
                    indicator = "*"
                robo_print("log", "  [%s] %s. %s - %s" % (indicator, i, recipe["name"], recipe["description"]))
            i += 1
        robo_print("log", "      A. Enable all recipe types.")
        robo_print("log", "      D. Disable all recipe types.")
        robo_print("log", "      Q. Quit without saving changes.")
        robo_print("log", "      S. Save changes and proceed.")
        choice = raw_input(
            "\nType a number to toggle the corresponding recipe "
            "type between ON [*] and OFF [ ].\nWhen you're satisfied "
            "with your choices, type an \"S\" to save and proceed: ")
        robo_print("log", "")
        if choice.upper() == "S":
            break
        elif choice.upper() == "A":
            for recipe in recipes:
                recipe["selected"] = True
        elif choice.upper() == "D":
            for recipe in recipes:
                recipe["selected"] = False
        elif choice.upper() == "Q":
            sys.exit(0)
        else:
            try:
                if recipes[int(choice)]["selected"] is False:
                    recipes[int(choice)]["selected"] = True
                else:
                    recipes[int(choice)]["selected"] = False
            except Exception:
                robo_print("error", "%s is not a valid option. Please try again.\n" % choice)


def generate_selected_recipes(prefs, recipes):
    """Generate the selected types of recipes.

    Args:
        prefs: TODO
        recipes: TODO
    """

    selected_recipe_count = 0
    for recipe in recipes:
        if recipe["buildable"] is True and recipe["selected"] is True:
            selected_recipe_count += 1

    if selected_recipe_count > 0:
        robo_print("log", "\nGenerating %s selected recipes..." %
                   selected_recipe_count)
    else:
        robo_print("log", "\nNo recipes selected.")

    for recipe in recipes:
        if (recipe["preferred"] is True and recipe["buildable"] is True and recipe["selected"] is True):
            # Write the recipe to disk.
            filename = "%s.%s.recipe" % (
                recipe["keys"]["Input"]["NAME"], recipe["name"])

            dest_dir = os.path.expanduser(prefs["RecipeCreateLocation"])
            create_dest_dirs(dest_dir)
            # TODO(Elliot): Warning if a file already exists here.
            dest_path = "%s/%s" % (dest_dir, filename)
            FoundationPlist.writePlist(recipe["keys"], dest_path)
            increment_recipe_count(prefs)

            robo_print("verbose", "    %s/%s" %
                       (prefs["RecipeCreateLocation"], filename))


def create_dest_dirs(path):
    """Creates the path to the recipe export location, if it doesn't exist.

    Args:
        path: TODO
    """

    dest_dir = os.path.expanduser(path)
    if not os.path.exists(dest_dir):
        try:
            os.makedirs(dest_dir)
        except Exception:
            robo_print("error", "Unable to create directory at %s." % dest_dir)


def extract_app_icon(icon_path, png_path):
    """Convert the app's icns file to 300x300 png at the specified path. 300x300 is Munki's preferred size, and 128x128 is Casper's preferred size, as of 2015-08-01.

    Args:
        icon_path: TODO
        png_path: TODO
    """

    png_path_absolute = os.path.expanduser(png_path)
    create_dest_dirs(os.path.dirname(png_path_absolute))

    # Add .icns if the icon path doesn't already end with .icns.
    if not icon_path.endswith(".icns"):
        icon_path = icon_path + ".icns"

    if not os.path.exists(png_path_absolute):
        cmd = "sips -s format png \"%s\" --out \"%s\" --resampleHeightWidthMax 300" % (
            icon_path, png_path_absolute)
        robo_print("debug", "Icon extraction command:")
        robo_print("debug", cmd)
        exitcode, out, err = get_exitcode_stdout_stderr(cmd)
        if exitcode == 0:
            robo_print("verbose", "    %s" % png_path)
        else:
            robo_print("error", err)


def congratulate(prefs):
    """Display a friendly congratulatory message upon creating recipes.

    Args:
        prefs: TODO
    """

    congrats_msg = (
        "That's awesome!",
        "Amazing.",
        "Well done!",
        "Good on ya!",
        "Thanks!",
        "Pretty cool, right?",
        "You rock star, you.",
        "Fantastic."
    )
    if prefs["RecipeCreateCount"] == 1:
        robo_print("log", "\nYou've now created your first recipe with Recipe Robot. Congratulations!\n")
    elif prefs["RecipeCreateCount"] > 1:
        robo_print("log", "\nYou've now created %s recipes with Recipe Robot. %s\n" % (
            prefs["RecipeCreateCount"], random.choice(congrats_msg)))


# TODO(Elliot): Make main() shorter. Just a flowchart for the logic.
def main():
    """Make the magic happen."""

    try:
        print_welcome_text()

        # Parse command line arguments, if any.
        argparser = build_argument_parser()
        args = argparser.parse_args()

        if args.include_existing is True:
            robo_print("warning", "Will offer to build recipes even if they already exist on GitHub. Please don't upload duplicate recipes.")
        if args.verbose is True:
            robo_print("verbose", "Verbose mode is on.")
            verbose_mode = True

        # Create the master recipe information list.
        recipes = init_recipes()

        # Read or create the user preferences.
        prefs = {}
        prefs = init_prefs(prefs, recipes, args)

        # Validate and process the input path.
        input_path = args.input_path
        input_path = input_path.rstrip("/ ")
        robo_print("log", "\nProcessing %s ..." % input_path)

        if input_path.startswith("http"):
            if input_path.find("github.com"):
                handle_github_url_input(input_path, recipes, args, prefs)
            if input_path.find("sourceforge.com"):
                handle_sourceforge_url_input(input_path, recipes, args, prefs)
            else:
                handle_download_url_input(input_path, recipes, args, prefs)
        elif input_path.startswith("ftp"):
            handle_download_url_input(input_path, recipes, args, prefs)
        elif os.path.exists(input_path):
            if input_path.endswith(".app"):
                handle_app_input(input_path, recipes, args, prefs)
            elif input_path.endswith(".download.recipe"):
                handle_download_recipe_input(input_path, recipes, args, prefs)
            elif input_path.endswith(".munki.recipe"):
                handle_munki_recipe_input(input_path, recipes, args, prefs)
            elif input_path.endswith(".pkg.recipe"):
                handle_pkg_recipe_input(input_path, recipes, args, prefs)
            elif input_path.endswith(".install.recipe"):
                handle_install_recipe_input(input_path, recipes, args, prefs)
            elif input_path.endswith(".jss.recipe"):
                handle_jss_recipe_input(input_path, recipes, args, prefs)
            elif input_path.endswith(".absolute.recipe"):
                handle_absolute_recipe_input(input_path, recipes, args, prefs)
            elif input_path.endswith(".sccm.recipe"):
                handle_sccm_recipe_input(input_path, recipes, args, prefs)
            elif input_path.endswith(".ds.recipe"):
                handle_ds_recipe_input(input_path, recipes, args, prefs)
            else:
                robo_print("error",
                           "I haven't been trained on how to handle this "
                           "input path:\n    %s" % input_path)
        else:
            robo_print("error",
                       "Input path does not exist. Please try again with a "
                       "valid input path.")

        if debug_mode is True:
            robo_print("debug", "ARGUMENT LIST:\n" + pprint.pformat(args) + "\n")
            robo_print("debug", "SUPPORTED DOWNLOAD FORMATS:\n" +
                       pprint.pformat(all_supported_formats) + "\n")
            robo_print("debug", "PREFERENCES:\n" + pprint.pformat(prefs) + "\n")
            robo_print("debug", "CURRENT RECIPE INFORMATION:\n" + pprint.pformat(recipes) + "\n")

        # Prompt the user with the available recipes types and let them choose.
        select_recipes_to_generate(recipes)

        # Create recipes for the recipe types that were selected above.
        generate_selected_recipes(prefs, recipes)

        # Pat on the back!
        congratulate(prefs)

    # Make sure to reset the terminal color with our dying breath.
    except (KeyboardInterrupt, SystemExit):
        print bcolors.ENDC
        print "Thanks for using Recipe Robot!"


if __name__ == '__main__':
    main()
