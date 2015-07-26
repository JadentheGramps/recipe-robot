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

usage: recipe-robot.py [-h] [-v] input_path [-o output_path] [-t recipe_type]

positional arguments:
    input_path            Path to a recipe or app you'd like to use as the
                          basis for creating AutoPkg recipes.

optional arguments:
    -h, --help            Show this help message and exit.
    -v, --verbose         Generate additional output about the process.
                          Verbose mode is off by default.
    -o, --output          Specify the folder in which to create output recipes.
                          This folder is ~/Library/Caches/Recipe Robot by
                          default.
    -t, --recipe-type     Specify the type(s) of recipe to create.
                          (e.g. download, pkg, munki, jss)
"""


import argparse
import os.path
import plistlib
from pprint import pprint
import random
import shlex
from subprocess import Popen, PIPE
import sys


# Global variables.
version = '0.0.1'
debug_mode = True  # set to True for additional output
prefs_file = os.path.expanduser(
    "~/Library/Preferences/com.elliotjordan.recipe-robot.plist")

# Build the list of download formats we know about.
# TODO: It would be great if we didn't need this list, but I suspect we do need
# it in order to tell the recipes which Processors to use.
# TODO(Elliot): This should probably not be a global variable.
supported_download_formats = ("dmg", "zip", "tar.gz", "gzip", "pkg")

# The name of the app for which a recipe is being built.
# TODO(Elliot): This should probably not be a global variable.
app_name = ""


# TODO(Elliot): Send bcolors.ENDC upon exception or keyboard interrupt.
# Otherwise people's terminal windows might get stuck in purple mode!


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


def get_exitcode_stdout_stderr(cmd):
    """Execute the external command and get its exitcode, stdout and stderr."""

    args = shlex.split(cmd)
    # TODO(Elliot): I've been told Popen is not a good practice. Better idea?
    proc = Popen(args, stdout=PIPE, stderr=PIPE)
    out, err = proc.communicate()
    exitcode = proc.returncode
    return exitcode, out, err


def build_argument_parser():
    """Build and return the argument parser for Recipe Robot."""

    parser = argparse.ArgumentParser(
        description="Easily and automatically create AutoPkg recipes.")
    parser.add_argument(
        "input_path",
        help="Path to a recipe or app to use as the basis for creating AutoPkg recipes.")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Generate additional output about the process.")
    # TODO(Elliot): Add --plist argument to header info up top.
    parser.add_argument(
        "--plist",
        action="store_true",
        help="Output all results as plists.")
    parser.add_argument(
        "-o", "--output",
        action="store",
        help="Path to a folder you'd like to save your generated recipes in.")
    parser.add_argument(
        "-t", "--recipe-type",
        action="store",
        help="The type(s) of recipe you'd like to generate.")
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

    print welcome_text


def init_recipes():
    """Store information related to each supported AutoPkg recipe type."""

    recipes = (
        {  # index 0
            "name": "download",
            "description": "Downloads an app in whatever format the developer provides."
        },
        {  # index 1
            "name": "munki",
            "description": "Imports into your Munki repository."
        },
        {  # index 2
            "name": "pkg",
            "description": "Creates a standard pkg installer file."
        },
        {  # index 3
            "name": "install",
            "description": "Installs the app on the computer running AutoPkg."
        },
        {  # index 4
            "name": "jss",
            "description": "Imports into your Casper JSS and creates necessary groups, policies, etc."
        },
        {  # index 5
            "name": "absolute",
            "description": "Imports into your Absolute Manage server."
        },
        {  # index 6
            "name": "sccm",
            "description": "Imports into your SCCM server."
        },
        {  # index 7
            "name": "ds",
            "description": "Imports into your DeployStudio Packages folder."
        }
    )

    # Set default values for all recipe types.
    for i in range(0, len(recipes)):
        recipes[i]["preferred"] = True
        recipes[i]["existing"] = False
        recipes[i]["buildable"] = False
        recipes[i]["keys"] = {
            "Identifier": "",
            "MinimumVersion": "0.5.0",
            "Input": {},
            "Process": ()
        }

    return recipes


def init_prefs(recipes):
    """Read from preferences plist, if it exists."""

    prefs = {}

    # If prefs file exists, try to read from it.
    if os.path.isfile(prefs_file):

        # Open the file.
        try:
            prefs = plistlib.readPlist(prefs_file)
        except Exception:
            print("There was a problem opening the prefs file. "
                  "Building new preferences.")
            prefs = build_prefs(prefs, recipes)

    else:
        print "No prefs file found. Building new preferences..."
        prefs = build_prefs(prefs, recipes)

    # Record last version number.
    prefs["LastRecipeRobotVersion"] = version

    # Write preferences to plist.
    plistlib.writePlist(prefs, prefs_file)

    return prefs


def build_prefs(prefs, recipes):
    """Prompt user for preferences, then save them back to the plist."""

    # TODO(Elliot): Make this something users can come back to and modify,
    # rather than just a first-run thing.

    # Prompt for and save recipe identifier prefix.
    prefs["RecipeIdentifierPrefix"] = "com.github.homebysix"
    print "\nRecipe identifier prefix"
    print "This is your default identifier, in reverse-domain notation.\n"
    choice = raw_input(
        "[%s]: " % prefs["RecipeIdentifierPrefix"])
    if choice != "":
        prefs["RecipeIdentifierPrefix"] = str(choice).rstrip(". ")

    # Prompt for recipe creation location.
    prefs["RecipeCreateLocation"] = "~/Library/AutoPkg/RecipeOverrides"
    print "\nLocation to save new recipes"
    print "This is where on disk your newly created recipes will be saved.\n"
    choice = raw_input(
        "[%s]: " % prefs["RecipeCreateLocation"])
    if choice != "":
        prefs["RecipeCreateLocation"] = str(choice).rstrip("/ ")

    # Prompt to set recipe types on/off as desired.
    prefs["RecipeTypes"] = []
    print "\nPreferred recipe types"
    print "Choose which recipe types will be offered to you by default.\n"
    # TODO(Elliot): Make this interactive while retaining scrollback.
    # Maybe with curses module?
    while True:
        for i in range(0, len(recipes)):
            if recipes[i]["preferred"] is False:
                indicator = " "
            else:
                indicator = "*"
            print "  [%s] %s. %s - %s" % (indicator, i, recipes[i]["name"], recipes[i]["description"])
        choice = raw_input(
            "\nType a number to toggle the corresponding recipe "
            "type between ON [*] and OFF [ ]. When you're satisfied "
            "with your choices, type an \"S\" to save and proceed: ")
        if choice.upper() == "S":
            break
        else:
            try:
                if recipes[int(choice)]["preferred"] is False:
                    recipes[int(choice)]["preferred"] = True
                else:
                    recipes[int(choice)]["preferred"] = False
            except Exception:
                print "%s%s is not a valid option. Please try again.%s\n" % (bcolors.ERROR, choice, bcolors.ENDC)

    for i in range(0, len(recipes)):
        if recipes[i]["preferred"] is True:
            prefs["RecipeTypes"].append(recipes[i]["name"])

    return prefs


def increment_recipe_count(prefs):
    """Add 1 to the cumulative count of recipes created by Recipe Robot."""

    prefs = plistlib.readPlist(prefs_file)
    prefs["RecipeCreateCount"] += 1
    plistlib.writePlist(prefs, prefs_file)


def get_input_type(input_path):
    """Determine the type of recipe generation needed based on path.

    Args:
        input_path: String path to an app, download recipe, etc.

    Returns:
        Int pseudo-enum value of InputType.
    """

    if input_path.endswith(".app"):
        return InputType.app
    elif input_path.endswith(".download.recipe"):
        return InputType.download_recipe
    elif input_path.endswith(".munki.recipe"):
        return InputType.munki_recipe
    elif input_path.endswith(".pkg.recipe"):
        return InputType.pkg_recipe
    elif input_path.endswith(".install.recipe"):
        return InputType.install_recipe
    elif input_path.endswith(".jss.recipe"):
        return InputType.jss_recipe
    elif input_path.endswith(".absolute.recipe"):
        return InputType.absolute_recipe
    elif input_path.endswith(".sccm.recipe"):
        return InputType.sccm_recipe
    elif input_path.endswith(".ds.recipe"):
        return InputType.ds_recipe


def create_existing_recipe_list(app_name, recipes):
    """Use autopkg search results to build existing recipe list."""

    # TODO(Elliot): Suggest users create GitHub API token to prevent limiting.
    # TODO(Elliot): Do search again without spaces in app names.
    # TODO(Elliot): Match results for apps with "!" in names. (e.g. Paparazzi!)
    cmd = "autopkg search -p %s" % app_name
    exitcode, out, err = get_exitcode_stdout_stderr(cmd)
    if exitcode == 0:
        # TODO(Elliot): There's probably a more efficient way to do this.
        # For each recipe type, see if it exists in the search results.
        for i in range(0, len(recipes)):
            search_term = "%s.%s.recipe" % (app_name, recipes[i]["name"])
            for line in out.split("\n"):
                if search_term in line:
                    # Set to False by default. If found, set to True.
                    recipes[i]["existing"] = True
    else:
        print err
        sys.exit(exitcode)


def create_buildable_recipe_list(app_name, recipes):
    """Add any preferred recipe types that don't already exist to the buildable
    list.
    """

    for i in range(0, len(recipes)):
        if recipes[i]["existing"] is False:
            if recipes[i]["preferred"] is True:
                recipes[i]["buildable"] = True


def handle_app_input(input_path, recipes):
    """Process an app, gathering required information to create a recipe."""

    app_name = ""
    sparkle_feed = ""
    min_sys_vers = ""

    print "Validating app..."
    try:
        info_plist = plistlib.readPlist(input_path + "/Contents/Info.plist")
    except Exception:
        print "This doesn't look like a valid app to me."
        if debug_mode is True:
            raise
        else:
            sys.exit(1)

    print "Determining app's name from CFBundleName..."
    try:
        app_name = info_plist["CFBundleName"]
    except KeyError:
        print "    This app doesn't have a CFBundleName. That's OK, we'll keep trying."

    if app_name == "":
        print "Determining app's name from CFBundleExecutable..."
        try:
            app_name = info_plist["CFBundleExecutable"]
        except KeyError:
            print "    This app doesn't have a CFBundleExecutable. The plot thickens."

    if app_name == "":
        print "Determining app's name from input path..."
        app_name = os.path.basename(input_path)[:-4]

    print "    App name is: %s" % app_name

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes)

    print "Checking for a Sparkle feed in SUFeeduRL..."
    try:
        sparkle_feed = info_plist["SUFeedURL"]
        # TODO(Elliot): Find out what format the Sparkle feed downloads in.
    except Exception:
        print "    No SUFeedURL found."

    if sparkle_feed == "":
        print "Checking for a Sparkle feed in SUOriginalFeedURL..."
        try:
            sparkle_feed = info_plist["SUOriginalFeedURL"]
            # TODO(Elliot): Find out what format the Sparkle feed downloads in.
        except Exception:
            print "    No SUOriginalFeedURL found."

    if sparkle_feed == "":
        print "    No Sparkle feed."
    else:
        print "    Sparkle feed is: %s" % sparkle_feed

    # TODO(Elliot): search_sourceforge_and_github(app_name)
    # TODO(Elliot): Find out what format the GH/SF feed downloads in.

    print "Checking for minimum OS version requirements..."
    try:
        min_sys_vers = info_plist["LSMinimumSystemVersion"]
    except Exception:
        print "    No LSMinimumSystemVersion found."

    # Send the information we discovered to the recipe keys.
    for i in range(0, len(recipes)):
        recipes[i]["keys"]["Input"]["NAME"] = app_name
        if recipes[i]["name"] == "download":
            if recipes[i]["buildable"] is True:
                recipes[i]["keys"]["Input"]["SPARKLE_FEED_URL"] = sparkle_feed
        if recipes[i]["name"] == "munki":
            if recipes[i]["buildable"] is True:
                recipes[i]["keys"]["Input"]["pkginfo"]["minimum_os_version"] = min_sys_vers


def handle_download_recipe_input(input_path, recipes):
    """Process a download recipe, gathering information useful for building
    other types of recipes.
    """

    # Read the recipe as a plist.
    input_recipe = plistlib.readPlist(input_path)

    print "Determining app's name from NAME input key..."
    app_name = input_recipe["Input"]["NAME"]
    print "    App name is: %s" % app_name

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes)

    # Get the download file format.
    # TODO(Elliot): Parse the recipe properly. Don't use grep.
    parsed_download_format = ""
    for download_format in supported_download_formats:
        cmd = "grep '.%s</string>' '%s'" % (download_format, input_path)
        exitcode, out, err = get_exitcode_stdout_stderr(cmd)
        if exitcode == 0:
            print "Looks like this recipe downloads a %s." % download_format
            parsed_download_format = download_format
            break

    # Send the information we discovered to the recipe keys.
    for i in range(0, len(recipes)):
        recipes[i]["keys"]["Input"]["NAME"] = app_name
        if recipes[i]["name"] == "pkg":
            if recipes[i]["buildable"] is True:
                if parsed_download_format == "dmg":
                    recipes[i]["Process"].append({
                        "Processor": "AppDmgVersioner",
                        "Arguments": {"dmg_path": "%pathname%"}}
                        # TODO(Elliot): Include the rest of the necessary keys for creating a pkg from a dmg download.
                    )
                elif parsed_download_format == "zip":
                    recipes[i]["Process"].append({
                        "Processor": "Unarchiver",
                        "Arguments": {"archive_path": "%pathname%",
                                      "destination_path": "%RECIPE_CACHE_DIR%/%NAME%/Applications",
                                      "purge_destination": True}}
                        # TODO(Elliot): Include the rest of the necessary keys for creating a pkg from a dmg download.
                    )
                else:
                    # TODO(Elliot): Construct keys for remaining supported download formats.
                    pass


def handle_munki_recipe_input(input_path, recipes):
    """Process a munki recipe, gathering information useful for building other
    types of recipes."""

    # Determine whether there's already a download Parent recipe.
    # If not, add it to the list of offered recipe formats.

    # Read the recipe as a plist.
    input_recipe = plistlib.readPlist(input_path)

    print "Determining app's name from NAME input key..."
    app_name = input_recipe["Input"]["NAME"]
    print "    App name is: %s" % app_name

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes)

    # If this munki recipe both downloads and imports the app, we
    # should offer to build a discrete download recipe with only
    # the appropriate sections of the munki recipe.

    # Offer to build pkg, jss, etc.

    # TODO(Elliot): Think about whether we want to dig into OS requirements,
    # blocking applications, etc when building munki recipes. I vote
    # yes, but it's probably not going to be easy.


def handle_pkg_recipe_input(input_path, recipes):
    """Process a pkg recipe, gathering information useful for building other
    types of recipes."""

    # Read the recipe as a plist.
    input_recipe = plistlib.readPlist(input_path)

    print "Determining app's name from NAME input key..."
    app_name = input_recipe["Input"]["NAME"]
    print "    App name is: %s" % app_name

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes)

    # Check to see whether the recipe has a download recipe as its parent. If
    # not, offer to build a discrete download recipe.

    # Offer to build munki, jss, etc.


def handle_install_recipe_input(input_path, recipes):
    """Process an install recipe, gathering information useful for building
    other types of recipes."""

    # Read the recipe as a plist.
    input_recipe = plistlib.readPlist(input_path)

    print "Determining app's name from NAME input key..."
    app_name = input_recipe["Input"]["NAME"]
    print "    App name is: %s" % app_name

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes)

    # Check to see whether the recipe has a download and/or pkg
    # recipe as its parent. If not, offer to build a discrete
    # download and/or pkg recipe.

    # Offer to build other recipes as able.


def handle_jss_recipe_input(input_path, recipes):
    """Process a jss recipe, gathering information useful for building other
    types of recipes."""

    # Read the recipe as a plist.
    input_recipe = plistlib.readPlist(input_path)

    print "Determining app's name from NAME input key..."
    app_name = input_recipe["Input"]["NAME"]
    print "    App name is: %s" % app_name

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes)

    # Check to see whether the recipe has a download and/or pkg
    # recipe as its parent. If not, offer to build a discrete
    # download and/or pkg recipe.

    # Offer to build other recipes as able.


def handle_absolute_recipe_input(input_path, recipes):
    """Process an absolute recipe, gathering information useful for building
    other types of recipes.
    """

    # Read the recipe as a plist.
    input_recipe = plistlib.readPlist(input_path)

    print "Determining app's name from NAME input key..."
    app_name = input_recipe["Input"]["NAME"]
    print "    App name is: %s" % app_name

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes)

    # Check to see whether the recipe has a download and/or pkg
    # recipe as its parent. If not, offer to build a discrete
    # download and/or pkg recipe.

    # Offer to build other recipes as able.


def handle_sccm_recipe_input(input_path, recipes):
    """Process a sccm recipe, gathering information useful for building other
    types of recipes."""

    # Read the recipe as a plist.
    input_recipe = plistlib.readPlist(input_path)

    print "Determining app's name from NAME input key..."
    app_name = input_recipe["Input"]["NAME"]
    print "    App name is: %s" % app_name

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes)

    # Check to see whether the recipe has a download and/or pkg
    # recipe as its parent. If not, offer to build a discrete
    # download and/or pkg recipe.

    # Offer to build other recipes as able.


def handle_ds_recipe_input(input_path, recipes):
    """Process a ds recipe, gathering information useful for building other
    types of recipes."""

    # Read the recipe as a plist.
    input_recipe = plistlib.readPlist(input_path)

    print "Determining app's name from NAME input key..."
    app_name = input_recipe["Input"]["NAME"]
    print "    App name is: %s" % app_name

    # Search for existing recipes that match the app's name.
    create_existing_recipe_list(app_name, recipes)

    # If supported recipe type doesn't already exist, mark as buildable.
    # The buildable list will be used to determine what is offered to the user.
    create_buildable_recipe_list(app_name, recipes)

    # Check to see whether the recipe has a download and/or pkg
    # recipe as its parent. If not, offer to build a discrete
    # download and/or pkg recipe.

    # Offer to build other recipes as able.


def search_sourceforge_and_github(app_name):
    """For apps that do not have a Sparkle feed, try to locate their project
    information on either SourceForge or GitHub so that the corresponding
    URL provider processors can be used to generate a recipe.
    """

    # TODO(Shea): Search on SourceForge for the project.
    #     If found, pass the project ID back to the recipe generator.
    #     To get ID: https://gist.github.com/homebysix/9640c6a6eecff82d3b16
    # TODO(Shea): Search on GitHub for the project.
    #     If found, pass the username and repo back to the recipe generator.


def generate_selected_recipes(prefs, recipes):
    """Generate the selected types of recipes."""

    for i in range(0, len(recipes)):
        if recipes[i]["buildable"] is True:  # TODO(Elliot): Change to "selectable" when that feature is built.

            print "Building %s.%s.recipe..." % (recipes[i]["keys"]["Input"]["NAME"], recipes[i]["name"])

            # Set the identifier of the recipe.
            recipes[i]["keys"]["Identifier"] = "%s.%s.%s" % (prefs["RecipeIdentifierPrefix"], recipes[i]["name"], app_name)

            # Set type-specific keys.
            if recipes[i]["name"] == "download":

                recipes[i]["keys"]["Description"] = "Downloads the latest version of %s." % recipes[i]["keys"]["Input"]["NAME"]

            elif recipes[i]["name"] == "munki":

                recipes[i]["keys"]["Description"] = "Imports the latest version of %s into Munki." % recipes[i]["keys"]["Input"]["NAME"]
                # We'll use this later when creating icons for Munki and JSS recipes.
                # cmd = 'sips -s format png \
                # "/Applications/iTunes.app/Contents/Resources/iTunes.icns" \
                # --out "/Users/elliot/Desktop/iTunes.png" \
                # --resampleHeightWidthMax 128'

            elif recipes[i]["name"] == "pkg":

                recipes[i]["keys"]["Description"] = "Downloads the latest version of %s and creates an installer package." % recipes[i]["keys"]["Input"]["NAME"]

            elif recipes[i]["name"] == "install":

                recipes[i]["keys"]["Description"] = "Installs the latest version of %s." % recipes[i]["keys"]["Input"]["NAME"]

            elif recipes[i]["name"] == "jss":

                recipes[i]["keys"]["Description"] = "Imports the latest version of %s into your JSS." % recipes[i]["keys"]["Input"]["NAME"]
                # We'll use this later when creating icons for Munki and JSS recipes.
                # cmd = 'sips -s format png \
                # "/Applications/iTunes.app/Contents/Resources/iTunes.icns" \
                # --out "/Users/elliot/Desktop/iTunes.png" \
                # --resampleHeightWidthMax 128'

            elif recipes[i]["name"] == "absolute":

                recipes[i]["keys"]["Description"] = "Imports the latest version of %s into Absolute Manage." % recipes[i]["keys"]["Input"]["NAME"]

            elif recipes[i]["name"] == "sccm":

                recipes[i]["keys"]["Description"] = "Imports the latest version of %s into SCCM." % recipes[i]["keys"]["Input"]["NAME"]

            elif recipes[i]["name"] == "ds":

                recipes[i]["keys"]["Description"] = "Imports the latest version of %s into DeployStudio." % recipes[i]["keys"]["Input"]["NAME"]
            else:
                print "I don't know how to generate a recipe of type %s." % recipes[i]["name"]

        # Write the recipe to disk.
        write_recipe_file(prefs, recipes[i]["keys"])


def write_recipe_file(prefs, keys):
    """Write a generated recipe to disk."""

    plist_path = prefs["RecipeCreateLocation"]
    recipe_file = os.path.expanduser(plist_path)
    plistlib.writePlist(keys, recipe_file)
    print "Wrote to: " + plist_path
    increment_recipe_count(prefs)
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
    print "You've now created %s recipes with Recipe Robot. %s" % (prefs["RecipeCreateCount"], random.choice(congrats_msg))


def print_debug_info(prefs, recipes):
    """Print current debug information."""

    print bcolors.DEBUG
    print "\n    RECIPE IDENTIFIER PREFIX: \n"
    print prefs["RecipeIdentifierPrefix"]
    print "\n    PREFERRED RECIPE TYPES\n"
    pprint(prefs["RecipeTypes"])
    print "\n    SUPPORTED DOWNLOAD FORMATS\n"
    pprint(supported_download_formats)
    print "\n    CURRENT RECIPE INFORMATION\n"
    pprint(recipes)
    print bcolors.ENDC


# TODO(Elliot): Make main() shorter. Just a flowchart for the logic.
def main():
    """Make the magic happen."""

    print_welcome_text()

    argparser = build_argument_parser()
    args = argparser.parse_args()

    # Temporary argument handling
    input_path = args.input_path
    input_path = input_path.rstrip("/ ")

    # TODO(Elliot): Verify that the input path actually exists.
    if not os.path.exists(input_path):
        print "%s[ERROR] Input path does not exist. Please try again with a valid input path.%s" % (
            bcolors.ERROR, bcolors.ENDC
        )
        sys.exit(1)

    recipes = init_recipes()
    prefs = init_prefs(recipes)

    input_type = get_input_type(input_path)
    print "\nProcessing %s ..." % input_path

    # Orchestrate helper functions to handle input_path's "type".
    if input_type is InputType.app:
        handle_app_input(input_path, recipes)
    elif input_type is InputType.download_recipe:
        handle_download_recipe_input(input_path, recipes)
    elif input_type is InputType.munki_recipe:
        handle_munki_recipe_input(input_path, recipes)
    elif input_type is InputType.pkg_recipe:
        handle_pkg_recipe_input(input_path, recipes)
    elif input_type is InputType.install_recipe:
        handle_install_recipe_input(input_path, recipes)
    elif input_type is InputType.jss_recipe:
        handle_jss_recipe_input(input_path, recipes)
    elif input_type is InputType.absolute_recipe:
        handle_absolute_recipe_input(input_path, recipes)
    elif input_type is InputType.sccm_recipe:
        handle_sccm_recipe_input(input_path, recipes)
    elif input_type is InputType.ds_recipe:
        handle_ds_recipe_input(input_path, recipes)
    else:
        print("%s[ERROR] I haven't been trained on how to handle this input "
              "path:\n    %s%s" % (bcolors.ERROR, input_path, bcolors.ENDC))
        sys.exit(1)

    print_debug_info(prefs, recipes)

    # Prompt the user with the available recipes types and let them choose.
    print "\nHere are the recipe types available to build:"
    for i in range(0, len(recipes)):
        print "    %s" % recipes[i]["name"]

    # Generate selected recipes.
    # generate_recipe("", dict())


if __name__ == '__main__':
    main()
