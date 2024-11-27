# -*- coding: utf-8 -*-
"""
*****************************************************************************************
 *                                                                                     *
*   Ce programme est un logiciel libre ; vous pouvez le redistribuer et/ou le modifier  *
*   selon les termes de la Licence Publique Générale GNU telle que publiée par          *
*   la Free Software Foundation ; soit la version 2 de la Licence, ou                   *
*   (à votre choix) toute version ultérieure.                                           *
 *                                                                                     *
*****************************************************************************************
"""
import shutil
import os
from pathlib import *
import xml.etree.ElementTree as ET
from qgis.core import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt import uic
from osgeo import gdal

from .ModeleListeCouches import ModeleListeCouches


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'QPackage_dialog_base.ui'))

class CopierRastersThread(QObject, QRunnable):
    progression_signal = pyqtSignal(float)  # Signal de progression
    finished_signal = pyqtSignal()  # Signal de fin
    error_signal = pyqtSignal(str)  # Signal d'erreur

    def __init__(self, layer, raster_path, new_raster_path):
        QObject.__init__(self)
        QRunnable.__init__(self)
        self.layer = layer
        self.raster_path = raster_path
        self.new_raster_path = new_raster_path
        self.chunk_size = 50 * 1024 * 1024  # 50 Mo

    def run(self):
        try:
            file_size = os.path.getsize(self.raster_path)
            copied_size = 0

            with open(self.raster_path, 'rb') as source_file:
                with open(self.new_raster_path, 'wb') as dest_file:
                    while True:
                        chunk = source_file.read(self.chunk_size)
                        if not chunk:
                            break
                        dest_file.write(chunk)
                        copied_size += len(chunk)

                        # Calcul de la progression
                        progression_value = copied_size / file_size
                        self.progression_signal.emit(progression_value)  # Émettre la progression

            self.finished_signal.emit()  # Copier terminée
        except Exception as e:
            self.error_signal.emit(str(e))  # Émettre l'erreur en cas de problème


class QPackageDialog(QDialog, FORM_CLASS):
    new_project_root: None
    copierCouchesTerminee = pyqtSignal()  # Signal pour indiquer la fin de copierCouches

    def __init__(self, iface, parent=None):

        # Liste des variables utilisables dans toute la classe
        self.raster_thread = None
        self.raster_worker = None
        self.copier_rasters_thread = None
        self.layer_path = None
        self.pas = None
        self.crs_origin = None
        self.projection = None
        self.forms_dir = None
        self.symbols_dir = None
        self.chemin = None
        self.not_checked_layers = None
        self.qgs_base_header = None
        self.checked_layers = None
        self.uri_source = None
        self.driver_name = None
        self.driver_map = None
        self.end_copy = None
        self.ordered_layers = None
        self.extensions_fichiers = None
        self.base_project = None
        self.base_project_path = None
        self.base_project_root = None
        self.base_project_name = None
        self.base_project_name_with_ext = None
        self.base_project_name_ext = None
        self.base_project_crs = None
        self.new_project = None
        self.new_project_path = None
        self.new_project_root = None
        self.new_project_name = None
        self.new_project_name_with_ext = None
        self.new_project_name_ext = None
        self.new_project_crs = None
        self.gpkg = None
        self.list_layers = []
        self.list_gpkg_layers = []
        self.gpkg_layer = None
        self.dirNameQgs = None
        self.dirNameQgz = None
        self.dirNameGpkg = None
        self.qgs_base_file_path = None
        self.tree_base = None
        self.root_base = None
        self.qgs_new_file_path = None
        self.tree_new = None
        self.root_new = None

        self.iface = iface

        self.thread_pool = QThreadPool()  # Initialise un pool de threads

        """Constructor."""
        super(QPackageDialog, self).__init__(parent)
        ui_path = os.path.join(os.path.dirname(__file__), 'QPackage_dialog_base.ui')
        uic.loadUi(ui_path, self)
        self.transform_context = QgsCoordinateTransformContext()

    def tr(self, message):
        return QCoreApplication.translate('QPackageDialog', message)

    def chercherRepertoire(self):
        self.chargerCouches()
        filename = QFileDialog.getExistingDirectory(
            self,
            caption=self.tr("Select the folder to pack the project into..."),
            directory=QDir.currentPath()
        )
        if filename:
            self._directory.setText(filename)

    def chargerCouches(self):
        #  Utilisation de Path pour le nom et chemin du projet en cours
        self.base_project = QgsProject.instance()
        # Chemin absolu mode binaire
        self.base_project_path = Path(self.base_project.fileName())
        # QgsMessageLog.logMessage(self.tr(f"self.base_project_path {str(self.base_project_path)}"), level=Qgis.Info)
        # Chemin racine
        self.base_project_root = self.base_project_path.parent
        # QgsMessageLog.logMessage(self.tr(f"self.base_project_root {str(self.base_project_root)}"), level=Qgis.Info)
        # Nom seul sans l'extension
        self.base_project_name = self.base_project_path.stem
        # QgsMessageLog.logMessage(self.tr(f"self.base_project_name {str(self.base_project_name)}"), level=Qgis.Info)
        # Nom avec l'extention
        self.base_project_name_with_ext = self.base_project_path.name
        # QgsMessageLog.logMessage(self.tr(f"self.base_project_name_with_ext {str(self.base_project_name_with_ext)}"), level=Qgis.Info)
        # Extension avec le .
        self.base_project_name_ext = self.base_project_path.suffix
        # QgsMessageLog.logMessage(self.tr(f"self.base_project_name_ext {str(self.base_project_name_ext)}"), level=Qgis.Info)
        # Récupérer le CRS du projet
        crs = QgsProject.instance().crs()
        self.crs_origin = crs.authid()  # Définit crs_origin sur l'instance
        # load the destination projection. if the selected item of the gui list is empty, we use the layer's one
        self.projection = self.crs_origin

        self._directory.setText('')
        self._projectname.setText(self.base_project_name)

        # self._listeprojections.clear()
        data = []
        for layer in QgsProject.instance().mapLayers().values():
            casecocher = QCheckBox(layer.name())
            if layer.type() == QgsMapLayer.VectorLayer:
                casecocher.setChecked(True)
            data.append(casecocher)
        self._tableau.setModel(ModeleListeCouches(data))
        # Réinitialiser la barre de progression après l'opération
        self._progression.setRange(0, 100)
        self._progression.setValue(0)

    def copierCouches(self):
        model = self._tableau.model()

        # Initialisation de la barre de progression
        nbrecouches = sum(1 for row in model.getDonnees() if row.isChecked())
        self.pas = int(100 / nbrecouches)
        progression = int(0)

        # Vérifications des répertoires et du projet
        if not self._directory.text() or not self._projectname.text():
            QMessageBox.critical(self, self.tr("Missing information"),
                                 self.tr("Please choose a destination directory and a project name"), QMessageBox.Ok)
            return

        QgsProject.instance().write()

        # Détermine le nom du projet et assure l'enregistrement au format qgz
        if self.base_project_name_ext == '.qgz' or self.base_project_name_ext == '.qgs':
            if self._projectname.text() == self.base_project_name:
                self.new_project_path = Path(str(os.path.join(self._directory.text(), self._projectname.text()) + '_pack.qgz'))
                # print('self.base_project_name_ext == ".qgz" - self._projectname.text() == self.base_project_name' + str(self.new_project_path))
            else:
                self.new_project_path = Path(str(os.path.join(self._directory.text(), self._projectname.text()) + '.qgz'))
                # print('self.base_project_name_ext == ".qgz" - self._projectname.text() != self.base_project_name' + str(self.new_project_path))

        # Crée une nouvelle instance de projet
        self.new_project = QgsProject.instance()
        self.new_project.setFileName(str(self.new_project_path))
        # QgsMessageLog.logMessage(self.tr(f"self.new_project.fileName() {self.new_project.fileName()}"), level=Qgis.Info)
        self.new_project_root = self.new_project_path.parent
        # Nom seul sans l'extension
        self.new_project_name = self.new_project_path.stem
        # QgsMessageLog.logMessage(self.tr(f"self.new_project_name {str(self.new_project_name)}"), level=Qgis.Info)
        # Nom avec l'extension
        self.new_project_name_with_ext = self.new_project_path.name
        # QgsMessageLog.logMessage(self.tr(f"self.new_project_name_with_ext {str(self.new_project_name_with_ext)}"), level=Qgis.Info)
        # Extension avec le point
        self.new_project_name_ext = self.new_project_path.suffix
        # QgsMessageLog.logMessage(self.tr(f"self.new_project_name_ext {str(self.new_project_name_ext)}"), level=Qgis.Info)
        self.new_project.write(os.path.join(self._directory.text(), self.new_project_name_with_ext))

        self.base_project_crs = self.base_project.crs()
        self.new_project.setCrs(self.base_project_crs)
        self.new_project_crs = self.new_project.crs()

        # Création des listes des couches cochées et non cochées
        self.checked_layers = []
        self.not_checked_layers = []

        # Récupération des couches du projet
        project_layers = QgsProject.instance().mapLayers()

        # Itération sur les lignes du modèle de données (couches dans l'interface)
        for row in model.getDonnees():
            # Comparaison avec les items de l'arbre des couches du projet
            for layer_id, layer in project_layers.items():
                # Si le nom de la couche correspond à celui de la ligne du modèle
                if layer.name() == row.text():
                    if row.isChecked():
                        # Ajouter aux couches cochées
                        self.checked_layers.append(layer)
                    else:
                        # Ajouter à la liste le nom des couches non cochées
                        self.not_checked_layers.append(layer.name())

        # Parcourir chaque couche non cochée dans le nouveau projet et la supprimer
        for layer_name in self.not_checked_layers:
            layer = QgsProject.instance().mapLayersByName(layer_name)
            if layer:
                self.new_project.removeMapLayer(layer[0])
                # print(f"La couche '{layer_name}' a été supprimée.")
            else:
                # print(f"La couche '{layer_name}' n'a pas été trouvée.")
                pass

        # self._progression.setMinimum(0)
        # self._progression.setMaximum(100)
        for layer in self.checked_layers:
            progression += self.pas
            # Traduisez le texte avec un modèle de formatage
            base_text = self.tr("Copying in progress: {0}%")
            # Remplacez le modèle de formatage avec la valeur réelle
            formatted_text = base_text.format(int(progression))
            # Mettez à jour le texte de la barre de progression
            self._progression.setFormat(formatted_text)
            self._progression.setValue(progression)

            # Met à jour le système de projection de la couche avec celui du projet
            crs = QgsCoordinateReferenceSystem(self.projection)
            layer.setCrs(crs, True)
            # Pour info, en cas de besoin : récupérer les différentes propriétés du CRS actuel
            # if layer:
            #     current_crs = layer.crs()
            #     proj4 = current_crs.toProj4()  # Code Proj4
            #     srsid = current_crs.srsid()  # ID interne SRS
            #     srid = current_crs.postgisSrid()  # SRID PostGIS
            #     epsg = current_crs.authid()  # Code EPSG, par exemple 'EPSG:4326'
            #     description = current_crs.description()  # Description du CRS
            #     projection_acronym = current_crs.projectionAcronym()  # Acronyme de la projection
            #     ellipsoid_acronym = current_crs.ellipsoidAcronym()  # Acronyme de l'ellipsoïde

            self.layer_path = Path(layer.source())
            # print('Chemin de la couche à traiter : ' + str(self.layer_path))
            try:
                file_extension = self.layer_path.suffixes[-1].lstrip('.')
            except:
                QgsMessageLog.logMessage(self.tr("file " + str(layer.name()) + " has no extension, cannot be copied"), level=Qgis.Info)
                pass
            if layer.type() == QgsMapLayer.VectorLayer and layer.dataProvider().name() == "ogr":
                # # Vérification si la couche est une couche en mémoire
                # if layer.isTemporary() or not self.layer_path.suffixes:
                #     # Gérer les couches en mémoire
                #     print("Couche memoire : " + str(layer.name()))
                #     self.driver_name = 'MEMORY'  # Utilisation d'un nom de driver fictif ou adapté
                # else:
                try:
                    file_extension = self.layer_path.suffixes[-1].lstrip('.')
                    if file_extension == 'vrt':
                        self.copy_vrt_file(layer)
                        continue
                    else:
                        self.driver_name = QgsVectorFileWriter.driverForExtension(file_extension)
                        # print('self.driver_name : ' + self.driver_name)
                except:
                    pass
                self.copy_vector_layer(layer, progression)
            # if the layer is a raster, the plugin must copy the file
            elif layer.type() == QgsMapLayer.RasterLayer:
                self.copy_raster_layer(layer)
                # Attendre la fin de tous les threads dans le QThreadPool
                self.thread_pool.waitForDone()
            # Copie et modification des chemins des éventuels fichiers annexes
            self.copy_annex_files(layer, progression)

        # Modifier les chemins des couches
        for layer in self.new_project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                if layer.dataProvider().name() == 'memory':
                    continue
                # Obtenir le chemin actuel
                chemin_actuel = Path(layer.dataProvider().dataSourceUri())
                if chemin_actuel != self.new_project_root:
                    nouveau_chemin = str(chemin_actuel.parent).replace(str(chemin_actuel.parent), str(self.new_project_root))
                    nouveau_chemin_complet = str(os.path.join(nouveau_chemin, chemin_actuel.stem) + str(chemin_actuel.suffix))
                    layer.setDataSource(nouveau_chemin_complet, layer.name(), layer.dataProvider().name())
            if isinstance(layer, QgsRasterLayer):
                if layer.dataProvider().name() == 'memory':
                    continue
                # Obtenir le chemin actuel
                chemin_actuel = Path(layer.dataProvider().dataSourceUri())
                if chemin_actuel != self.new_project_root:
                    nouveau_chemin = str(chemin_actuel.parent).replace(str(chemin_actuel.parent), str(self.new_project_root))
                    nouveau_chemin_complet = str(os.path.join(nouveau_chemin, chemin_actuel.stem) + str(chemin_actuel.suffix))
                    layer.setDataSource(nouveau_chemin_complet, layer.name(), layer.dataProvider().name())

        self._progression.setFormat(self.tr('Packaging completed'))
        self._progression.setRange(0, 100)
        self._progression.setValue(0)
        # Sauvegarder les modifications dans le projet
        self.new_project.write(str(self.new_project_path))
        QgsMessageLog.logMessage(self.tr("Operation completed successfully"), level=Qgis.Info)

        self.copierCouchesTerminee.emit()


    def replaceText(self, node, newText):
        if node is None or node.text is None:
            raise Exception(self.tr("Node not contain text"))
        # Remplacer le texte directement
        node.text = newText


    def copy_vrt_file(self, layer):
        vrt_file_path = str(self.layer_path)
        # Création du chemin du fichier VRT mis à jour
        new_vrt_file_path = Path(self.new_project_root) / self.layer_path.name
        shutil.copy(vrt_file_path, new_vrt_file_path)
        # print(f"fichier {vrt_file_path} copié dans {new_vrt_file_path}.")

        # # Ouvrir le fichier VRT avec GDAL pour vérifier s'il s'agit d'un raster ou d'un vecteur
        # vrt_dataset = gdal.Open(vrt_file_path)
        # if vrt_dataset is not None:
        #     print(f"Ouvrir {vrt_file_path} en tant que fichier raster.")
        #     layer_type = "raster"
        # else:
        #     print(f"Ouvrir {vrt_file_path} en tant que fichier vectoriel.")
        #     vrt_dataset = gdal.OpenEx(vrt_file_path, gdal.OF_VECTOR)
        #     if vrt_dataset is None:
        #         print(f"Impossible d'ouvrir le fichier VRT : {vrt_file_path}")
        #         return
        #     layer_type = "vector"

        # Analyse du fichier VRT pour identifier les fichiers sources
        tree = ET.parse(vrt_file_path)
        root = tree.getroot()
        vrt_dir = Path(vrt_file_path).parent

        for datasource in root.findall(".//SrcDataSource"):
            src_file_rel = datasource.text
            src_file_abs = (vrt_dir / src_file_rel).resolve()  # Chemin absolu du fichier source
            src_file_name = os.path.basename(src_file_abs)
            new_src_file_path = Path(self.new_project_root) / src_file_name

            # Copier le fichier source vers le répertoire de destination
            if src_file_abs.exists():
                try:
                    shutil.copy(src_file_abs, new_src_file_path)
                    # Mettre à jour le chemin dans le VRT avec le nouveau chemin relatif
                    datasource.text = new_src_file_path.name

                except Exception as e:
                    QgsMessageLog.logMessage(self.tr(f"Error copying source file {src_file_abs} : {e}"), level=Qgis.Warning)
            else:
                QgsMessageLog.logMessage(self.tr(f"Source file {src_file_abs} was not copied."), level=Qgis.Warning)


    def copy_vector_layer(self, layer, progression):
        """Copier une couche vectorielle vers le répertoire de destination en remplaçant l'existante si nécessaire et l'ajouter au projet."""
        uri = layer.dataProvider().dataSourceUri()
        # Vérifier si la couche est une couche en mémoire
        if layer.isTemporary() or not layer.source():
            # Si la couche est en mémoire, elle doit être directement ajoutée au nouveau projet
            # print(self.tr(f"The '{layer.name()}' layer is in memory. It will be added to the new project directly."))
            # Ajouter la couche en mémoire au nouveau projet
            self.new_project.addMapLayer(layer)
            QgsMessageLog.logMessage(self.tr(f"Memory layer {layer.name()} added to the project."), level=Qgis.Info)
        elif "gpkg" in uri.lower() or "sqlite" in uri.lower():
            # Extraire le chemin de la base SQLite ou gpkg (avant le délimiteur "|")
            chemin_base = uri.split('|')[0]
            # Déterminer le chemin cible
            nom_fichier = os.path.basename(chemin_base)
            # Construction du chemin absolu
            new_path = os.path.join(self.new_project_root, nom_fichier)
            # Copier la base de données
            shutil.copy(chemin_base, new_path)
            QgsMessageLog.logMessage(self.tr((f"Database copied from {chemin_base} to {new_path} and added to project")), level=Qgis.Info)
            # print(f"Base de données copiée : {chemin_base} -> {new_path}")
        else:
            chemin = Path(layer.source())

            # Construction du chemin absolu
            new_path = os.path.join(self.new_project_root, chemin.name)
            new_path = os.path.abspath(new_path)  # S'assurer que le chemin est absolu

            # Supprimer le fichier existant si présent
            if os.path.exists(new_path):
                os.remove(new_path)
                # print(f"Le fichier existant {new_path} a été supprimé.")

            # Supprimer les fichiers auxiliaires (si format Shapefile ou mapinfo)
            base_name = os.path.splitext(new_path)[0]
            for ext in ['.shx', '.dbf', '.prj', '.cpg', '.qpj', '.tab', '.dat', '.map', '.id']:
                aux_file = base_name + ext
                if os.path.exists(aux_file):
                    os.remove(aux_file)
                    # print(f"Le fichier auxiliaire existant {aux_file} a été supprimé.")

            # Vérifier si le fichier source existe
            if not os.path.exists(layer.source()):
                self.show_warning_popup(f"The source file {layer.source()} does not exist.")
                return

            # Configurer les options de sauvegarde
            options = QgsVectorFileWriter.SaveVectorOptions()

            options.driverName = self.driver_name
            options.fileEncoding = "UTF-8"
            options.layerOptions = ["ENCODING=UTF-8"]

            # Contexte de transformation des coordonnées basé sur le CRS de la couche source
            context = QgsCoordinateTransformContext()

            # Copier la couche avec writeAsVectorFormatV3
            error = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer,
                new_path,
                context,
                options
            )

            if error[0] != QgsVectorFileWriter.NoError:
                self.show_warning_popup(self.tr(
                    f"Error writing file from {layer.source()} to {new_path} : {error[1]}"))
                return
            else:
                QgsMessageLog.logMessage(self.tr(f"File successfully created in: {new_path}"), level=Qgis.Info)
            # Vérifier si le fichier a été créé
            if not os.path.exists(new_path):
                self.show_warning_popup(self.tr(f"The file {new_path} was not created."))
                return

    def copy_raster_layer(self, layer):
        """Copier une couche raster vers le répertoire de destination."""
        raster_path = Path(layer.publicSource())
        if not os.path.exists(raster_path):
            self.show_warning_popup(raster_path)
            return

        new_raster_path = os.path.join(self.new_project_root, raster_path.name)
        if raster_path == new_raster_path:
            QgsMessageLog.logMessage(
                self.tr(f"Source and destination for {layer.name()} are the same, skipping copy."),
                level=Qgis.Warning
            )
            return

        # Test de la taille du fichier
        file_size = os.path.getsize(raster_path)
        if file_size > 1e9 / 2:
            # Afficher la boîte de dialogue pour demander l'action à l'utilisateur
            self.choice_action_for_big_raster(layer, raster_path, new_raster_path)
        else:
            self.start_raster_copy(layer, raster_path, new_raster_path)  # Si fichier < 500 Mo, copier directement

    def choice_action_for_big_raster(self, layer, raster_path, new_raster_path):
        """Afficher une boîte de dialogue pour demander l'action de l'utilisateur."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(self.tr("Large raster packaging"))
        msg_box.setText(self.tr(
            "The raster {} is large and may take a long time to copy. What do you want to do?"
        ).format(raster_path.name))

        copy_button = msg_box.addButton(self.tr("Copy"), QMessageBox.AcceptRole)
        keep_button = msg_box.addButton(self.tr("Stop copy but keep in project"), QMessageBox.DestructiveRole)
        remove_button = msg_box.addButton(self.tr("Stop copy and remove in project"), QMessageBox.RejectRole)
        msg_box.exec_()

        reply = msg_box.clickedButton()

        if reply == copy_button:
            # Créer un worker et le connecter aux signaux du thread principal
            self.raster_worker = CopierRastersThread(layer, raster_path, new_raster_path)
            self.raster_worker.progression_signal.connect(self.update_progression)
            self.raster_worker.finished_signal.connect(self.on_copier_couches_terminee)
            self.raster_worker.error_signal.connect(self.on_copy_error)

            # Démarrer le thread
            self.raster_thread = QThread()
            self.raster_worker.moveToThread(self.raster_thread)
            self.raster_thread.started.connect(self.raster_worker.run)
            self.raster_thread.start()

            # Bloquer l'interface jusqu'à la fin de la copie
            loop = QEventLoop()  # Créer une boucle d'événement locale
            self.raster_worker.finished_signal.connect(loop.quit)  # Arrêter la boucle quand c'est terminé
            loop.exec_()  # Attendre la fin du thread

            # Ne pas afficher le message avant la fin de la copie
            QgsMessageLog.logMessage(
                self.tr("Raster {} copied successfully.").format(raster_path.name),
                level=Qgis.Info
            )

        elif reply == keep_button:
            QgsMessageLog.logMessage(
                self.tr("Raster {} is not copied, but kept in the project.").format(raster_path.name),
                level=Qgis.Info
            )

        elif reply == remove_button:
            self.new_project.removeMapLayer(layer)
            QgsMessageLog.logMessage(
                self.tr("Raster {} removed from project.").format(raster_path.name),
                level=Qgis.Warning
            )

    def start_raster_copy(self, layer, raster_path, new_raster_path):
        """Démarrer le thread de copie pour le raster."""
        self.raster_worker = CopierRastersThread(layer, raster_path, new_raster_path)
        self.raster_worker.progression_signal.connect(self.update_progression)
        self.raster_worker.finished_signal.connect(self.on_copier_couches_terminee)
        self.raster_worker.error_signal.connect(self.on_copy_error)

        self.raster_thread = QThread()
        self.raster_worker.moveToThread(self.raster_thread)
        self.raster_thread.started.connect(self.raster_worker.run)
        self.raster_thread.start()

    def update_progression(self, progression_value):
        """Mise à jour de la barre de progression en fonction de la valeur."""
        percentage = int(progression_value * 100)  # Convertir la progression en pourcentage
        # Mettre à jour la barre de progression avec le pourcentage
        self._progression.setValue(percentage)
        # Mettre à jour le format de la barre de progression avec le texte et le pourcentage
        formatted_text = self.tr("Copy of the raster: {}%").format(percentage)
        self._progression.setFormat(formatted_text)

        # Optionnel : Afficher le message de progression dans le journal d'information pour le débogage
        # QgsMessageLog.logMessage(f"Progression: {percentage}%", level=Qgis.Info)
    def on_copier_couches_terminee(self):
        """Méthode appelée lorsque la copie est terminée."""
        self._progression.setValue(100)  # Assurer que la barre de progression est à 100% à la fin
        self._progression.setFormat(self.tr("Raster layer copied successfully."))  # Réinitialiser le texte de la barre de progression

    def on_copy_error(self, error_message):
        """Méthode appelée lorsqu'une erreur se produit pendant la copie."""
        QgsMessageLog.logMessage(
            self.tr("Error during raster copy: {}").format(error_message),
            level=Qgis.Critical
        )
        # Afficher une boîte de dialogue d'erreur à l'utilisateur
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(self.tr("Error"))
        msg_box.setText(self.tr("An error occurred during the copy: {}").format(error_message))
        msg_box.exec_()
        self._progression.setFormat('')
        self._progression.setValue(0)  # Réinitialiser la barre de progression en cas d'erreur


    def copy_annex_files(self, layer, progression):
        """Copier les fichiers SVG référencés dans un fichier QML de style vers un sous-dossier 'symbols' dans le répertoire du nouveau projet."""
        self.symbols_dir = os.path.join(self.new_project_root, 'symbols')
        self.forms_dir = os.path.join(self.new_project_root, 'forms')
        # Mise à jour des chemins dans le renderer QGIS

        # def update_svg_paths_in_renderer(renderer, symbol=None):
        #     """Mise à jour des chemins SVG pour les renderers."""
        #     if isinstance(renderer, QgsEmbeddedSymbolRenderer):
        #         symbol = renderer.symbol()
        #     elif isinstance(renderer, QgsCategorizedSymbolRenderer):
        #         QgsMessageLog.logMessage(self.tr("Updating Categorized Renderer"), level=Qgis.Info)
        #         for category in renderer.categories():
        #             symbol = category.symbol()
        #     elif isinstance(renderer, QgsRuleBasedRenderer):
        #         QgsMessageLog.logMessage(self.tr("Updating Rule-Based Renderer"), level=Qgis.Info)
        #         root_rule = renderer.rootRule()
        #         process_rule(root_rule)
        #     elif isinstance(renderer, QgsSingleSymbolRenderer):
        #         symbol = renderer.symbol()
        #     if symbol is not None:
        #         print('symbol : ' + str(symbol))
        #         # Créer le sous-dossier symbols s'il n'existe pas
        #         # os.makedirs(self.symbols_dir, exist_ok=True)
        #         # copy_svg_and_update_paths(symbol)
        #         copy_resources_and_update_paths(symbol)

        def update_paths_in_renderer(renderer, symbol=None):
            """Mise à jour des chemins des ressources pour les renderers."""
            if isinstance(renderer, QgsEmbeddedSymbolRenderer):
                symbol = renderer.symbol()
            elif isinstance(renderer, QgsCategorizedSymbolRenderer):
                for category in renderer.categories():
                    symbol = category.symbol()
                    if symbol is not None:
                        copy_resources_and_update_paths(symbol)
            elif isinstance(renderer, QgsRuleBasedRenderer):
                root_rule = renderer.rootRule()
                process_rule(root_rule)
            elif isinstance(renderer, QgsSingleSymbolRenderer):
                symbol = renderer.symbol()
            if symbol is not None:
                copy_resources_and_update_paths(symbol)


        def copy_resources_and_update_paths(symbol):
            """Mise à jour des chemins SVG, raster et des informations sur les polices dans les symboles."""
            resources_to_copy = []

            for i in range(symbol.symbolLayerCount()):
                symbol_layer = symbol.symbolLayer(i)

                # Gestion des SVG
                if isinstance(symbol_layer, QgsSvgMarkerSymbolLayer):
                    old_svg_path = Path(symbol_layer.path())
                    resources_to_copy.append((old_svg_path, old_svg_path.name, 'svg'))

                # Gestion des raster
                elif isinstance(symbol_layer, QgsRasterMarkerSymbolLayer):
                    # Obtenir le chemin du fichier raster via ses propriétés
                    raster_path = symbol_layer.path()
                    if raster_path:
                        old_raster_path = Path(raster_path)
                        resources_to_copy.append((old_raster_path, old_raster_path.name, 'raster'))
                    else:
                        QgsMessageLog.logMessage(
                            self.tr("Raster marker symbol layer detected but no raster path found."),
                            level=Qgis.Warning
                        )

                # Gestion des polices
                elif isinstance(symbol_layer, QgsFontMarkerSymbolLayer):
                    font_family = symbol_layer.fontFamily()
                    glyph = symbol_layer.character()

                    # Documenter les polices utilisées
                    document_fonts_used(font_family, glyph)

                    QgsMessageLog.logMessage(
                        self.tr(f"Font-based symbol detected: Font = {font_family}, Glyph = {glyph}"),
                        level=Qgis.Info
                    )

            # Copier les fichiers détectés
            for old_path, file_name, resource_type in resources_to_copy:
                try:
                    # Créer le dossier 'symbols' s'il n'existe pas
                    os.makedirs(self.symbols_dir, exist_ok=True)

                    # Nouveau chemin pour le fichier copié
                    new_path = os.path.join(self.symbols_dir, file_name)

                    # Copier le fichier
                    shutil.copy2(old_path, new_path)

                    # Mettre à jour le chemin dans le symbole
                    if resource_type == 'svg':
                        symbol_layer.setPath(new_path)
                    elif resource_type == 'raster':
                        symbol_layer.setPath(new_path)

                except Exception as e:
                    QgsMessageLog.logMessage(
                        self.tr(f"Error copying {old_path} to {new_path}: {e}"),
                        level=Qgis.Warning
                    )

        def document_fonts_used(font_family, glyph):
            """Documenter les polices utilisées dans un fichier texte."""
            # Créer le dossier symbols s'il n'existe pas encore
            os.makedirs(self.symbols_dir, exist_ok=True)

            # Chemin vers le fichier fonts_used.txt
            fonts_file = os.path.join(self.symbols_dir, "fonts_used.txt")

            # Ajouter une ligne pour la police détectée
            with open(fonts_file, "a", encoding="utf-8") as f:
                f.write(f"Font: {font_family}, Glyph: {glyph}\n")


        def copy_svg_and_update_paths(symbol):
            """Mise à jour des chemins SVG dans les symboles."""
            # for i in range(symbol.symbolLayerCount()):
            #     svg_symbol_layer = symbol.symbolLayer(i)
            #     if isinstance(svg_symbol_layer, QgsSvgMarkerSymbolLayer):
            #         old_svg_path = Path(svg_symbol_layer.path())
            #         svg_name = old_svg_path.name
            #         new_svg_path = os.path.join(self.symbols_dir, svg_name)
            #         shutil.copy2(old_svg_path, new_svg_path)
            #         svg_symbol_layer.setPath(new_svg_path)

            svg_files_to_copy = []
            svg_symbol_layer = None
            for i in range(symbol.symbolLayerCount()):
                svg_symbol_layer = symbol.symbolLayer(i)
                if isinstance(svg_symbol_layer, QgsSvgMarkerSymbolLayer):
                    old_svg_path = Path(svg_symbol_layer.path())
                    svg_files_to_copy.append((old_svg_path, old_svg_path.name))

            # Si des fichiers SVG sont détectés, créer le dossier et copier les fichiers
            if svg_files_to_copy:
                os.makedirs(self.symbols_dir, exist_ok=True)

                for old_svg_path, svg_name in svg_files_to_copy:
                    new_svg_path = os.path.join(self.symbols_dir, svg_name)
                    shutil.copy2(old_svg_path, new_svg_path)
                    svg_symbol_layer.setPath(new_svg_path)


        def process_rule(rule, visited_rules=None):
            """Fonction récursive pour traiter les règles imbriquées."""
            if visited_rules is None:
                visited_rules = set()
            if rule in visited_rules:
                return  # Évite la boucle infinie si on revisite la même règle
            visited_rules.add(rule)
            symbol = rule.symbol()
            if symbol is None:
                QgsMessageLog.logMessage(self.tr("No symbol found for rule: {}").format(rule), level=Qgis.Warning)
            else:
                copy_resources_and_update_paths(symbol)
                # copy_svg_and_update_paths(symbol)
            # Récursion pour les règles enfants
            for child_rule in rule.children():
                process_rule(child_rule)

        try:
            if not layer or not layer.isValid(): # Si un gros fichier a été supprimé du projet
                return
        except:
            return

        # Appliquer les mises à jour aux renderers
        l_renderer = layer.renderer()
        # update_svg_paths_in_renderer(l_renderer)
        update_paths_in_renderer(l_renderer)

        if layer.type() == QgsMapLayer.VectorLayer:
            # Lire la configuration du formulaire d'édition
            form_config = layer.editFormConfig()

            # Obtenir le chemin du fichier du formulaire d'édition
            origin_form_path = Path(form_config.uiForm())

            # Lire et modifier la balise editforminitfilepath
            init_file_path = form_config.initFilePath()
            origin_init_file_path = Path(init_file_path)

            # Vérifier si le chemin du fichier du formulaire d'édition est valide
            if origin_form_path.is_file():
                # Créer le sous-dossier forms s'il n'existe pas
                os.makedirs(self.forms_dir, exist_ok=True)
                # Copier le fichier du formulaire UI vers le sous-dossier forms
                form_file_name = os.path.basename(origin_form_path)
                new_form_path = os.path.join(self.forms_dir, form_file_name)
                try:
                    # Copier le fichier de formulaire d'édition
                    shutil.copy2(origin_form_path, new_form_path)
                    form_config.setUiForm(str(new_form_path))  # Modifier le chemin du formulaire d'édition
                except PermissionError as e:
                    QgsMessageLog.logMessage(self.tr(f"Permission error copying from {origin_form_path} to {new_form_path}: {e}"), level=Qgis.Warning)
            else:
                if str(origin_form_path) != '.':
                    QgsMessageLog.logMessage(self.tr(f"The path {str(origin_form_path)} is invalid."), level=Qgis.Warning)
                pass

            # Vérifier si le chemin du fichier initForm est valide
            if origin_init_file_path.is_file():
                # Copier le fichier editforminitfilepath vers le sous-dossier forms
                init_file_name = os.path.basename(origin_init_file_path)
                new_init_file_path = os.path.join(self.forms_dir, init_file_name)
                try:
                    # Copier le fichier d'initialisation
                    shutil.copy2(origin_init_file_path, new_init_file_path)
                    form_config.setInitFilePath(str(new_init_file_path))  # Modifier le chemin du fichier init
                except PermissionError as e:
                    QgsMessageLog.logMessage(
                        self.tr(f"Permission error copying {origin_init_file_path} to {new_init_file_path}: {e}"), level=Qgis.Warning)
            else:
                QgsMessageLog.logMessage(self.tr(f"The path {str(origin_init_file_path)} is not a valid file."), level=Qgis.Warning)
                # print(f"Le chemin {str(origin_init_file_path)} n'est pas un fichier valide.")
            # Appliquer les modifications de la configuration à la couche (si nécessaire)
            layer.setEditFormConfig(form_config)  # Appliquer la nouvelle configuration du formulaire
        else: # Si ce n'est pas une couche vectorielle, on passe
            pass

        # Facultatif : Si votre couche nécessite une validation/sauvegarde explicite
        # layer.commitChanges()

        # Assurez-vous que la mise à jour n'est appelée qu'une seule fois
        if not hasattr(layer, 'is_updated'):
            layer.is_updated = True
            # Rafraîchir la couche pour appliquer les changements
            layer.triggerRepaint()
        QgsMessageLog.logMessage(self.tr("All side files and/or svg symbols have been copied and their paths updated successfully."), level=Qgis.Info)


    def show_warning_popup(self, missing_path):
        """Afficher une fenêtre d'alerte pour les chemins manquants."""
        message = self.tr(
            "{}' was not found. Please check the file path or the drive letter.").format(missing_path)
        # Inscription du fichier non trouvé dans le journal :
        QgsMessageLog.logMessage(message, level=Qgis.Warning)

