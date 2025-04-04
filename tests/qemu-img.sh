#! /usr/bin/env nix-shell
#! nix-shell -i bash -p coreutils qemu parted e2fsprogs dosfstools debootstrap grub2 util-linux

# The Linux bootstrapper
#
# Bootstrap Linux distribution in chroot or QEMU.
#
# TODO:
# - Common
#   - Use unpriv tools
#     - qcow2fuse
#     - fakechroot fakeroot debootstrap (--variant=fakechroot)
#   - Move to Rust + YAML
#   - Split off chroot from qemu img
#   - Select distro ansible-like YAML config
#     - bootstrapper: debootstrap, pacstrap
#     - sources.list (see ansible.builtin.apt_repository)
#     - shared dir
#     - Log in over SSH?
#     - QEMU opts:
#       - partition_table: GPT, MBR
#       - bootloader_mode: BIOS, EFI
#       - bootloader: grub
#       - shared devs
#       - Log in over serial?
#       - vdisk_size: amt of bytes
#       - vdisk_format: qcow2, raw
#       - vdisk_partitions (see community.general.parted)
# - QEMU side
#   - Test logging in over serial
#   - Test GPT/BIOS
#   - Grub CFG Ansible-like config
#   - Discuss EFI/OVMF?
#   - Test in CI
#   - a bunch of the options should be not none
# - Chroot side
#   - What to mount
#   - Test in CI in QEMU
#   - a bunch of the options should be default or none

set -e -x -o nounset

########### Notes ###########
#
# - You don't have to use Nix to run this script; just be sure to have the above packages installed.
#
# - [This Stack Overflow post](https://unix.stackexchange.com/questions/719367)
#    implies that EFI does not work without extra firmware (e.g., OVMF) and
#    emulated flash memory, but BIOS on GPT should. [This Gentoo
#    Wiki](https://wiki.gentoo.org/wiki/QEMU#Preparation_of_a_bootable_disk_image_from_scratch)
#    page suggests that BIOS on MBR will work. Their original scripts didn't
#    work, and no combination of {(EFI, GPT), (BIOS, GPT), (BIOS, MBR)} x
#    {Ubuntu, Debian} implemented in this script seems to work.
#
# - This script will call sudo. If I can get this version to work, I will
#   consider modifying it to not requires super-user.
#
# - Invoke like `./qemu-img.sh 2>&1 | tee log` to get a debugging log.

########### Inputs ###########
QEMU_ARCH="${QEMU_ARCH:-x86_64}"
IMAGE="${IMAGE:-qemu-debian}"
IMAGE_SIZE="${QEMU_IMAGE_SIZE:-20G}"
DEBIAN_ARCH="${DEBIAN_ARCH:-amd64}"
DEBIAN_VARIANT="${DEBIAN_VARIANT:-debian}"
GRUB_MODE="${GRUB_MODE:-bios}"
PARTITION_TABLE="${PARTITION_TABLE:-mbr}"
ROOT_FS="${ROOT_FS:-ext4}"
HOSTNAME="${QEMU_HOSTNAME:-qemu-debian}"

########### Input validation ###########

if [[ "$DEBIAN_VARIANT" != "ubuntu" && "$DEBIAN_VARIANT" != "debian" ]]; then
    echo "Invalid DEBIAN_VARIANT: Choose 'ubuntu' or 'debian'"
    exit 1
fi

if [[ "$GRUB_MODE" != "bios" && "$GRUB_MODE" != "efi" ]]; then
    echo "Invalid GRUB_MODE: Choose 'bios' or 'efi'"
    exit 1
fi

if [[ "$PARTITION_TABLE" != "gpt" && "$PARTITION_TABLE" != "mbr" ]]; then
    echo "Invalid PARTITION_TABLE: Choose 'gpt' or 'mbr'"
    exit 1
fi
if [ "$DEBIAN_VARIANT" = "ubuntu" ]; then
  DEBIAN_MIRROR=http://us.archive.ubuntu.com/ubuntu/
  DEBIAN_COMPONENTS="main,restricted,universe,multiverse"
  DEBIAN_VERSION=jammy
  DEBIAN_COMPONENTS_SPACE=$(echo $DEBIAN_COMPONENTS | tr , ' ')
  DEBIAN_SOURCES="
deb $DEBIAN_MIRROR $DEBIAN_VERSION         $DEBIAN_COMPONENTS_SPACE
deb $DEBIAN_MIRROR $DEBIAN_VERSION-updates $DEBIAN_COMPONENTS_SPACE
"
else
  # Try docker run --rm debian:bookworm sh -c 'apt-get update && apt-get install -y netselect-apt && netselect-apt'
  DEBIAN_MIRROR=http://ftp.us.debian.org/debian/
  DEBIAN_COMPONENTS="main,contrib,non-free,non-free-firmware"
  DEBIAN_VERSION=bookworm
  DEBIAN_COMPONENTS_SPACE=$(echo $DEBIAN_COMPONENTS | tr , ' ')
  DEBIAN_SOURCES="
deb $DEBIAN_MIRROR                              $DEBIAN_VERSION         $DEBIAN_COMPONENTS_SPACE
deb $DEBIAN_MIRROR                              $DEBIAN_VERSION-updates $DEBIAN_COMPONENTS_SPACE
deb https://security.debian.org/debian-security $DEBIAN_VERSION-security $DEBIAN_COMPONENTS_SPACE
"
fi


########### Create QEMU image ###########
MOUNT_DIR="$(mktemp --directory)"
rm --force "${IMAGE}.raw" "${IMAGE}.qcow2"
qemu-img create -f raw "${IMAGE}.raw" "$IMAGE_SIZE"
LOOP_DEV=$(sudo losetup --show --find "${IMAGE}.raw")

########### Create disk partitions ###########
# See https://wiki.archlinux.org/title/Partitioning
# See https://wiki.archlinux.org/title/Parted
if   [ "$PARTITION_TABLE" = gpt ] && [ "$GRUB_MODE" = bios ]; then
  # https://unix.stackexchange.com/questions/719367/configure-grub-to-load-in-qemu
  sudo parted --script "$LOOP_DEV" \
    mklabel gpt \
    mkpart non-fs '0%' 550MiB \
    set 1 bios_grub on \
    mkpart primary "$ROOT_FS" 550MiB 100% \
    print
  ROOT_PART="${LOOP_DEV}p2"
elif [ "$PARTITION_TABLE" = gpt ] && [ "$GRUB_MODE" = efi ]; then
  # https://unix.stackexchange.com/a/719958/59973
  sudo parted --script "$LOOP_DEV" \
    mklabel gpt \
    mkpart efi fat32 '0%' 550MiB \
    set 1 esp on \
    mkpart primary "$ROOT_FS" 550MiB 100% \
    print
  BOOT_PART="${LOOP_DEV}p1"
  ROOT_PART="${LOOP_DEV}p2"
elif [ "$PARTITION_TABLE" = mbr ] && [ "$GRUB_MODE" = bios ]; then
  # https://wiki.gentoo.org/wiki/QEMU#Preparation_of_a_bootable_disk_image_from_scratch
  sudo parted --script "$LOOP_DEV" \
    mklabel msdos \
    mkpart primary "$ROOT_FS" 1MiB 100% \
    set 1 boot on \
    print
  ROOT_PART="${LOOP_DEV}p1"
elif [ "$PARTITION_TABLE" = mbr ] && [ "$GRUB_MODE" = efi ]; then
  echo "Not supported"
  exit 1
fi

if [ "${BOOT_PART:-}" ]; then
  BOOT_UUID="$(blkid -s UUID -o value "${BOOT_PART}")"
fi
ROOT_UUID="$(blkid -s UUID -o value "${ROOT_PART}")"
sudo fdisk -l "$LOOP_DEV"
sudo partprobe "$LOOP_DEV"
sudo "mkfs.$ROOT_FS" -L root "$ROOT_PART"

########### Mount fs ###########
lsblk -o NAME,UUID,PARTUUID,LABEL,PARTLABEL,MOUNTPOINT
sudo mkdir --parents "$MOUNT_DIR"
sudo mount "$ROOT_PART" "$MOUNT_DIR"
if [ -n "${BOOT_PART:-}" ]; then
  sudo mkdir --parents "$MOUNT_DIR/boot/efi"
  sudo mount "$BOOT_PART" "$MOUNT_DIR/boot/efi"
fi

########### Run debootstrap ###########
if [ "$GRUB_MODE" = efi ]; then
  if [ "$DEBIAN_ARCH" = amd64 ]; then
    grub_target=x86_64-efi
  else
    grub_target="$DEBIAN_ARCH-efi"
  fi
  # sudo grub-install "--target=$grub_target" "--efi-directory=$MOUNT_DIR/boot/efi" --bootloader-id=debian "$LOOP_DEV"
  grub_args="--target=$grub_target --efi-directory=/boot/efi --bootloader-id=debian"
  grub_pkg="grub-$DEBIAN_ARCH-efi"
else
  if [ "$DEBIAN_ARCH" = amd64 ]; then
    grub_target=i386-pc
  else
    grub_target="$DEBIAN_ARCH-pc"
  fi
  # sudo grub-install "--target=$grub_target" "--boot-directory=$MOUNT_DIR/boot/grub" "$LOOP_DEV"
  grub_args="--target=$grub_target --boot-directory=/boot"
  grub_pkg=grub-pc
fi
if [ "$DEBIAN_VARIANT" = ubuntu ]; then
  linux_pkg=linux-image-generic
else
  if [ "$DEBIAN_ARCH" = i386 ]; then
    linux_pkg="linux-image-686-pae"
  else
    linux_pkg="linux-image-$DEBIAN_ARCH"
  fi
fi
mkdir --parents /tmp/debootstrap
sudo debootstrap \
  "--arch=$DEBIAN_ARCH" \
  "--include=$linux_pkg,$grub_pkg,systemd,systemd-sysv,ping,nano" \
  --cache-dir=/tmp/debootstrap \
  --variant=minbase \
  "--components=$DEBIAN_COMPONENTS" \
  "$DEBIAN_VERSION" "$MOUNT_DIR" "$DEBIAN_MIRROR"

########### Set up required files ###########
# Following https://wiki.debian.org/chroot

# Prevents dpkg from starting daemons in the chroot
# cat <<EOF | sudo tee "$MOUNT_DIR/usr/sbin/policy-rc.d"
# #!/bin/sh
# exit 101
# EOF
# sudo chmod a+x "$MOUNT_DIR/usr/sbin/policy-rc.d"

# The ischroot command is buggy and does not detect that it is running in a chroot
sudo cp "${MOUNT_DIR}/bin/true" "${MOUNT_DIR}/usr/bin/ischroot"

# See https://wiki.archlinux.org/title/EFI_system_partition#Typical_mount_points
# See https://wiki.archlinux.org/title/Fstab#Identifying_file_systems
# I promise not to mount any drives with the same label in this QMEU VM.
if [ -n "${BOOT_UUID:-}" ]; then
  cat <<EOF | sudo tee "$MOUNT_DIR/etc/fstab"
UUID=$BOOT_UUID  /boot/efi  vfat      defaults           0  2
EOF
fi
cat <<EOF | sudo tee --append "$MOUNT_DIR/etc/fstab"
UUID=$ROOT_UUID  /          $ROOT_FS  errors=remount-ro  0  1
EOF

echo "$HOSTNAME" | sudo tee "$MOUNT_DIR/etc/hostname"

cat <<EOF | sudo tee "$MOUNT_DIR/etc/hosts"
127.0.0.1       localhost $HOSTNAME
::1             localhost ip6-localhost ip6-loopback $HOSTNAME
ff02::1         ip6-allnodes
ff02::2         ip6-allrouters
EOF

echo "$DEBIAN_SOURCES" | sudo tee "$MOUNT_DIR/etc/apt/sources.list"

# sudo cp /etc/resolv.conf "$MOUNT_DIR/etc/resolv.conf"

cat <<EOF | sudo tee "$MOUNT_DIR/chroot-install.sh"
#!/usr/bin/env bash
set -e -x

# Set up root user
echo "root:root" | chpasswd

# Install GRUB
apt-get install --reinstall --yes $grub_pkg
grub-install $grub_args "$LOOP_DEV"
update-grub

ls /
ls /boot

# Debugging
grep menuentry /boot/grub/grub.cfg
grep vmlinuz   /boot/grub/grub.cfg
grep initrd    /boot/grub/grub.cfg
exit
EOF
sudo chmod +x "$MOUNT_DIR/chroot-install.sh"

########### Configure system inside chroot ###########
# See https://wiki.archlinux.org/title/Chroot#Using_chroot
# See https://superuser.com/questions/165116/mount-dev-proc-sys-in-a-chroot-environment
# See https://askubuntu.com/questions/1122975/difference-between-rbind-and-bind-in-mounting
# See https://superuser.com/a/111215/110096
sudo mount -t proc                     /proc "$MOUNT_DIR/proc"
sudo mount -t sysfs                    /sys  "$MOUNT_DIR/sys"
sudo mount --make-rslave --rbind       /dev  "$MOUNT_DIR/dev"
# sudo mount --make-rslave --rbind       /run  "$MOUNT_DIR/run"
sudo chroot "$MOUNT_DIR" /usr/bin/env "PATH=/bin:/sbin" /chroot-install.sh
sudo grep menuentry "$MOUNT_DIR/boot/grub/grub.cfg"
sudo grep vmlinuz "$MOUNT_DIR/boot/grub/grub.cfg"
sudo grep initrd "$MOUNT_DIR/boot/grub/grub.cfg"


########### Clean up ###########
sudo rm "$MOUNT_DIR/chroot-install.sh"
# sudo rm "$MOUNT_DIR/usr/sbin/policy-rc.d"
sudo rm "${MOUNT_DIR}/bin/true" "${MOUNT_DIR}/usr/bin/ischroot"
sudo umount --recursive "$MOUNT_DIR"
sudo losetup --detach "$LOOP_DEV"
rmdir "$MOUNT_DIR"

########### Run ###########
"qemu-system-$QEMU_ARCH" \
  -drive file="${IMAGE}.raw",format=raw \
  -nographic \
  -m 4G \
  -serial mon:stdio

########### Fancier run ###########
# qemu-img convert -f raw -O qcow2 "${IMAGE}.raw" "${IMAGE}.qcow2"
# rm --force "${IMAGE}.raw"
# mkdir --parents shared
# "qemu-system-$QEMU_ARCH" \
#   -cpu host \
#   -enable-kvm \
#   -hda "${IMAGE}.qcow2" \
#   -virtfs "local,path=$PWD/shared,mount_tag=host0,security_model=mapped,id=host0" \
#   -boot d \
#   -nographic \
#   -serial mon:stdio \
#   -m 4G
# root=/dev/sda1
#
