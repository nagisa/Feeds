# Trifle installation instructions

Check if there's no package named `trifle` in official and/or unofficial
(AUR, PPA) repositories available. Install from there if available.

## Building and installing

```sh
git clone git://github.com/simukis/Feeds.git # Getting sources
cd Feeds
sudo python3 setup.py install # Actual installation
cd ..
sudo rm -r Feeds
```
