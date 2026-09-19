#!/usr/bin/env bash
# Install the bundled SDLC skill by host profile or legacy project arguments.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
profile=""
profile_set=0
scope="project"
mode="copy"
target=""
client_dir=""
home_root=""
destination_root=""
dry_run=0
json_output=0
link_alias=0
mode_set=0

die() {
  echo "$1" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || die "--profile requires a value"; profile="$2"; profile_set=1; shift 2 ;;
    --scope) [[ $# -ge 2 ]] || die "--scope requires a value"; scope="$2"; shift 2 ;;
    --mode) [[ $# -ge 2 ]] || die "--mode requires a value"; mode="$2"; mode_set=1; shift 2 ;;
    --client-dir) [[ $# -ge 2 ]] || die "--client-dir requires a value"; client_dir="$2"; shift 2 ;;
    --home-root) [[ $# -ge 2 ]] || die "--home-root requires a value"; home_root="$2"; shift 2 ;;
    --destination-root) [[ $# -ge 2 ]] || die "--destination-root requires a value"; destination_root="$2"; shift 2 ;;
    --link) link_alias=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    --json) json_output=1; shift ;;
    --*) die "Unexpected argument: $1" ;;
    *)
      [[ -z "$target" ]] || die "Unexpected argument: $1"
      target="$1"
      shift
      ;;
  esac
done

if [[ "$link_alias" -eq 1 && "$mode_set" -eq 1 && "$mode" != "link" ]]; then
  die "--link conflicts with --mode $mode."
fi
[[ "$link_alias" -eq 0 ]] || mode="link"
[[ "$scope" == "project" || "$scope" == "global" ]] || die "Invalid --scope: $scope"
[[ "$mode" == "copy" || "$mode" == "link" ]] || die "Invalid --mode: $mode"

if [[ -n "$profile" && -n "$client_dir" ]]; then
  die "--profile cannot be combined with legacy --client-dir."
fi
if [[ -z "$profile" ]]; then
  profile="generic-agent-skills"
fi
case "$profile" in
  copilot-vscode|claude-code|generic-agent-skills) ;;
  *) die "Unknown profile: $profile" ;;
esac

if [[ -n "$client_dir" || ( -n "$target" && "$profile_set" -eq 0 ) ]]; then
  scope="project"
  [[ -n "$target" ]] || die "Legacy --client-dir requires a target project."
  [[ -n "$client_dir" ]] || client_dir=".agents/skills"
  [[ "$client_dir" != /* && "$client_dir" != *\\* ]] || die "--client-dir must be a safe relative path."
  case "/$client_dir/" in */../*|*/./*) die "--client-dir must be a safe relative path." ;; esac
  destination_root="$target/$client_dir"
fi

if [[ "$scope" == "project" ]]; then
  [[ -n "$target" ]] || die "Project scope requires a target project."
  [[ -d "$target" ]] || die "Target project path not found: $target"
else
  [[ -n "$home_root" ]] || die "Global scope requires explicit --home-root."
fi

args=("$script_dir/qualify.py" install --profile "$profile" --scope "$scope" --mode "$mode")
[[ -z "$target" ]] || args+=(--project-root "$target")
[[ -z "$home_root" ]] || args+=(--home-root "$home_root")
[[ -z "$destination_root" ]] || args+=(--destination-root "$destination_root")
[[ "$dry_run" -eq 0 ]] || args+=(--dry-run)

output="$(python "${args[@]}")"
if [[ "$json_output" -eq 1 ]]; then
  printf '%s\n' "$output"
else
  if [[ "$dry_run" -eq 1 ]]; then verb="Would install"; elif [[ "$mode" == "link" ]]; then verb="Linked"; else verb="Copied"; fi
  printf '%s\n' "$verb the sdlc suite for $profile ($scope/$mode)." >&2
  printf '%s\n' "Reload the client and confirm sdlc and its sdlc-* implementations are discovered." >&2
fi
