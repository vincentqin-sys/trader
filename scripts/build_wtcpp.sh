cd ./app/wtcpp/src
bash build_release.sh
cd ..
bash copy_bins_linux.sh ../wtpy
pip install ../wtpy
cd ../../
