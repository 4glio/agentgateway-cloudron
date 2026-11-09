package trivy

# Policy for test/trivy-scan.sh, applied with --ignore-policy.
#
# This is NOT an allowlist. A finding that reaches this file is a whole CLASS of
# finding that cannot apply to this artefact, decided once and argued in place,
# rather than an ID that somebody has to add every time the database moves. Per
# finding exceptions belong in .trivyignore, where each line is a claim about one
# advisory and carries its own removal condition.
#
# The policy is evaluated once per vulnerability with that vulnerability as input,
# and returns true to ignore it.

default ignore = false

# Kernel advisories reported against linux-libc-dev.
#
# cloudron/base installs the kernel headers (linux-libc-dev) because other
# packages build against them, and that package carries the version of the
# Ubuntu kernel source it was cut from. Trivy maps every kernel advisory fixed in
# a newer kernel to it, which on a current base is several hundred HIGH and
# CRITICAL findings per release.
#
# None of them can be exploited here: a container does not ship or run a kernel.
# The kernel that would have to be vulnerable is the host's, and it is Cloudron's
# to patch, not this image's. The headers are plain constants and struct
# definitions with no executable code from the kernel.
#
# Removal condition: this rule goes away if the base stops shipping
# linux-libc-dev, or if Trivy starts attributing kernel advisories to a running
# kernel package in the image instead.
ignore {
  input.PkgName == "linux-libc-dev"
}
