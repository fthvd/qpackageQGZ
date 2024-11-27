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
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import *

# Initialiser les ressources Qt à partir du fichier resources.py
from .resources import *
# Importer le code pour le dialogue
from .QPackage_dialog import QPackageDialog
import os.path


class QPackage:
    """QGIS Plugin Implementation."""
    global crs_origin
    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'QPackage_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)


        # Create the dialog (after translation) and keep reference
        self.dlg = QPackageDialog(iface)
        self.dlg.setWindowFlags(self.dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        self.dlg.setWindowTitle(self.tr("QPackage"))
        self.dlg._charger.setText(self.tr("Load layers of the current project"))
        self.dlg._directory_button.setText(self.tr("Destination folder"))
        self.dlg.label_2.setText(self.tr("Project name: "))
        self.dlg._copy.setText(self.tr("Copy the layers"))

        # Déclarer les attributs d'instance
        self.actions = []
        self.menu = self.tr(u'&QPackage')
        # TODO : Nous allons permettre à l'utilisateur de configurer cela dans une future itération
        self.toolbar = self.iface.addToolBar(self.tr(u'QPackage'))
        self.toolbar.setObjectName(u'QPackage')

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Obtenir la traduction d'une chaîne en utilisant l'API de traduction Qt.

        Nous implémentons cela nous-mêmes car nous n'héritons pas de QObject.

        :param message: Chaîne pour la traduction.
        :type message: str, QString

        :returns: Version traduite du message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('QPackage', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Ajouter une icône de la barre d'outils à la barre d'outils.

        :param icon_path: Chemin vers l'icône pour cette action. Peut être un chemin de ressource
            (par exemple ':/plugins/foo/bar.png') ou un chemin normal du système de fichiers.
        :type icon_path: str

        :param text: Texte qui doit être affiché dans les éléments de menu pour cette action.
        :type text: str

        :param callback: Fonction à appeler lorsque l'action est déclenchée.
        :type callback: function

        :param enabled_flag: Un indicateur indiquant si l'action doit être activée par défaut. Par défaut à True.
        :type enabled_flag: bool

        :param add_to_menu: Indicateur indiquant si l'action doit également être ajoutée au menu. Par défaut à True.
        :type add_to_menu: bool

        :param add_to_toolbar: Indicateur indiquant si l'action doit également être ajoutée à la barre d'outils. Par défaut à True.
        :type add_to_toolbar: bool

        :param status_tip: Texte optionnel à afficher dans une info-bulle lorsque le pointeur de la souris survole l'action.
        :type status_tip: str

        :param parent: Widget parent pour la nouvelle action. Par défaut None.
        :type parent: QWidget

        :param whats_this: Texte optionnel à afficher dans la barre d'état lorsque le pointeur de la souris survole l'action.

        :returns: L'action qui a été créée. Notez que l'action est également ajoutée à la liste self.actions.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Créer les entrées de menu et les icônes de la barre d'outils dans l'interface QGIS."""

        icon_path = ':/plugins/QPackage/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'QPackage'),
            callback=self.run,
            parent=self.iface.mainWindow())


    def unload(self):
        """Supprimer l'élément de menu du plugin et l'icône de l'interface QGIS."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&QPackage'),
                action)
            self.iface.removeToolBarIcon(action)
        # Supprimer la barre d'outils
        del self.toolbar

    def run(self):
        """Méthode run qui exécute toutes les tâches nécessaires."""
        self.dlg.chargerCouches()
        # Utiliser self.dlg.crs_origin initialisé dans la routine chargerCouches() de QPackage_dialog.py
        if self.dlg.crs_origin:
            self.dlg.label.setText(self.tr('CRS of project is') + f' {self.dlg.crs_origin}')
            # self.dlg.label.setText(self.tr(f'CRS of project is {self.dlg.crs_origin}'))
        else:
            self.dlg.label.setText(self.tr("CRS of project could not be determined"))

        if os.path.isfile(QgsProject.instance().fileName()):
            strproject = os.path.basename(QgsProject.instance().fileName())
            self.dlg._projectname.setText(strproject[:(len(strproject) - 4)])

        # Connecter le signal copierCouchesTerminee à la méthode afficherMessageFin
        self.dlg.copierCouchesTerminee.connect(self.afficherMessageFin)

        # Afficher le dialogue principal
        self.dlg.show()
        self.dlg.activateWindow()

    def afficherMessageFin(self):
        """Afficher la boîte de message lorsque copierCouches est terminé et fermer la fenêtre principale."""
        msg_box = QMessageBox()
        msg_box.setWindowFlags(self.dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        msg_box.setWindowTitle(self.tr("QPackage"))
        msg_box.setText(self.tr("Operation completed successfully. The new packaged project was opened automatically"))

        # ouvrir_button = msg_box.addButton(self.tr("Open"), QMessageBox.ActionRole)
        quitter_button = msg_box.addButton(self.tr("Quit"), QMessageBox.RejectRole)

        # Afficher la boîte de dialogue en mode modale
        msg_box.exec_()

        # Gérer les actions basées sur le bouton cliqué
        # if msg_box.clickedButton() == ouvrir_button:
        #     # Utiliser QgsProject.instance().read() pour ouvrir le projet
        #     QgsProject.instance().read(str(self.dlg.new_project_path))
        if msg_box.clickedButton() == quitter_button:
            QgsMessageLog.logMessage(self.tr("The user chose to quit the plugin"),
                                     level=Qgis.Info)

        # Effacer _directory
        self.dlg._directory.setText('')
        self.dlg._progression.setFormat('')
        # Fermer la fenêtre principale après avoir traité l'action utilisateur
        self.dlg.close()

        # Déconnecter le signal copierCouchesTerminee pour empêcher tout futur déclenchement
        self.dlg.copierCouchesTerminee.disconnect(self.afficherMessageFin)

        # Quitter la méthode pour éviter toute exécution supplémentaire
        return
