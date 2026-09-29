import os
import sys
import subprocess
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterFile,
    QgsProcessingException,
    QgsProcessingProvider
)

class GeotiffToPmtilesAlgorithm(QgsProcessingAlgorithm):
    LEFT_INPUT = 'LEFT_INPUT'
    RIGHT_INPUT = 'RIGHT_INPUT'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return GeotiffToPmtilesAlgorithm()

    def name(self):
        return 'geotifftopmtiles'

    def displayName(self):
        return self.tr('Convert GeoTIFF to PMTiles')

    def group(self):
        return self.tr('PMTiles Tools')

    def groupId(self):
        return 'pmtilestools'

    def shortHelpString(self):
        return self.tr(
            "This plugin converts left and right GeoTIFFs into PMTiles format for the Stereo PMTiles Viewer. / 本プラグインは、Stereo PMTiles Viewerで閲覧・表示するための左右GeoTIFFをPMTiles形式に一括変換します。<br><br>"
            "Select `Left GeoTiff` for the Left Image and `Right GeoTiff` for the Right Image. / 左画像に `left.tif`、右画像に `right.tif` を指定します。<br>"
            "Select the output folder and click `Run`. `left.pmtiles` and `right.pmtiles` will be created automatically. / 保存先フォルダを選択し、`実行` をクリックすると、フォルダ内に `left.pmtiles` と `right.pmtiles` が生成されます。<br><br>"
            "You can use <a href='https://yiwasa.github.io/StereoPMTilesViewer/'>the Stereo PMTiles Viewer</a> to view stereo images. / 生成された画像は<a href='https://yiwasa.github.io/StereoPMTilesViewer/'>the Stereo PMTiles Viewer</a>で閲覧できます。<br>"
            "To generate stereo GeoTIFFs, please use the Stereo MPI-RRIM Creator QGIS plugin.  / 左右のステレオGeoTIFFの作成にはStereo MPI-RRIM Creator等のプラグインをご利用ください<br>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.LEFT_INPUT,
                self.tr('左画像 (Left GeoTIFF)')
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.RIGHT_INPUT,
                self.tr('右画像 (Right GeoTIFF)')
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.OUTPUT_FOLDER,
                self.tr('保存先フォルダ（※必須）'),
                behavior=__import__('qgis').core.Qgis.ProcessingFileParameterBehavior.Folder,
                optional=False
            )
        )

    def ensure_dependencies(self, feedback):
        """必要なライブラリがQGIS内蔵Pythonにインストールされているか確認し、なければ自動インストールする"""
        try:
            import site
            if site.USER_SITE not in sys.path:
                sys.path.append(site.USER_SITE)
            import rio_pmtiles
            import rasterio
            feedback.pushInfo("必要なライブラリ (rasterio, rio-pmtiles) は既にインストールされています。")
        except ImportError:
            feedback.pushInfo("必要なライブラリが見つかりません。QGIS環境への自動インストールを開始します（数分かかる場合があります）...")
            try:
                # QGISが動いているPythonの実行ファイル(sys.executable)でpipを呼び出す
                python_exe = sys.executable
                if 'qgis' in python_exe.lower() or not python_exe.endswith(('python', 'python.exe', 'python3')):
                    if os.name == 'nt':
                        python_exe = os.path.join(sys.exec_prefix, 'python.exe')
                    else:
                        import shutil
                        python_exe = os.path.join(sys.exec_prefix, 'bin', 'python3')
                        if not os.path.exists(python_exe):
                            python_exe = shutil.which('python3') or 'python3'
                cmd = [python_exe, "-m", "pip", "install", "--upgrade", "rasterio", "rio-pmtiles", "pmtiles"]
                
                process = subprocess.Popen(  # nosec
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=os.environ.copy()
                )
                
                for line in process.stdout:
                    feedback.pushInfo(line.strip())
                    
                process.wait()
                if process.returncode != 0:
                    raise Exception("pip install command returned non-zero exit code.")
                    
                feedback.pushInfo("ライブラリのインストールが正常に完了しました。")
            except Exception as e:
                raise QgsProcessingException(f"ライブラリの自動インストールに失敗しました: {e}\n管理者権限でQGISを起動して再試行してください。")

    def processAlgorithm(self, parameters, context, feedback):
        left_layer = self.parameterAsRasterLayer(parameters, self.LEFT_INPUT, context)
        right_layer = self.parameterAsRasterLayer(parameters, self.RIGHT_INPUT, context)
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)

        if left_layer is None or right_layer is None:
            raise QgsProcessingException(self.tr('左右のレイヤを正しく指定してください'))

        if not output_folder or not os.path.isdir(output_folder):
            raise QgsProcessingException(self.tr('保存先フォルダを正しく指定してください'))

        left_path = left_layer.source()
        right_path = right_layer.source()

        left_output = os.path.join(output_folder, "left.pmtiles")
        right_output = os.path.join(output_folder, "right.pmtiles")

        # 1. 依存関係のチェックと自動インストール
        self.ensure_dependencies(feedback)

        # 2. 変換処理の実行
        python_exe = sys.executable
        if 'qgis' in python_exe.lower() or not python_exe.endswith(('python', 'python.exe', 'python3')):
            if os.name == 'nt':
                python_exe = os.path.join(sys.exec_prefix, 'python.exe')
            else:
                import shutil
                python_exe = os.path.join(sys.exec_prefix, 'bin', 'python3')
                if not os.path.exists(python_exe):
                    python_exe = shutil.which('python3') or 'python3'

        def run_conversion(in_path, out_path, name):
            feedback.pushInfo(f"\n【{name}の変換を開始】: {out_path}")
            command = [
                python_exe, "-c",
                "import sys; from rasterio.rio.main import main_group; sys.argv[0]='rio'; sys.exit(main_group())",
                "pmtiles",
                in_path,
                out_path,
                "--format", "JPEG",
                "--tile-size", "512"
            ]

            process = subprocess.Popen(  # nosec
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=os.environ.copy()
            )

            for line in process.stdout:
                feedback.pushInfo(line.strip())
                if feedback.isCanceled():
                    process.terminate()
                    break

            process.wait()
            
            if process.returncode != 0:
                raise QgsProcessingException(f"{name}の変換に失敗しました（エラーコード: {process.returncode}）")

        try:
            run_conversion(left_path, left_output, "左画像")
            run_conversion(right_path, right_output, "右画像")
        except Exception as e:
            raise QgsProcessingException(f"予期せぬエラーが発生しました: {e}")

        feedback.pushInfo("\nすべての処理が完了しました！")
        return {self.OUTPUT_FOLDER: output_folder}


class PMTilesConverterPlugin:
    def __init__(self):
        self.provider = None

    def initProcessing(self):
        from qgis.core import QgsApplication
        self.provider = PMTilesProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

    def unload(self):
        from qgis.core import QgsApplication
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

class PMTilesProvider(QgsProcessingProvider):
    def loadAlgorithms(self, *args, **kwargs):
        self.addAlgorithm(GeotiffToPmtilesAlgorithm())

    def id(self):
        return 'pmtilesconverter'

    def name(self):
        return 'PMTiles Converter'