package xcosaicompiler;

import java.awt.datatransfer.*;
import java.awt.dnd.*;
import java.io.*;
import java.nio.file.*;
import java.util.List;

public class XcosDropHandler extends DropTargetAdapter {

    private final String tmpFilePath;

    public XcosDropHandler(String tmpFilePath) {
        this.tmpFilePath = tmpFilePath;
    }

    @Override
    public void drop(DropTargetDropEvent event) {
        try {
            event.acceptDrop(DnDConstants.ACTION_COPY);
            Transferable t = event.getTransferable();

            if (t.isDataFlavorSupported(DataFlavor.javaFileListFlavor)) {
                @SuppressWarnings("unchecked")
                List<File> files = (List<File>)
                    t.getTransferData(DataFlavor.javaFileListFlavor);

                StringBuilder sb = new StringBuilder();
                for (File f : files) {
                    sb.append(f.getAbsolutePath()).append("\n");
                }

                // Write file list
                Files.writeString(Path.of(tmpFilePath),
                                  sb.toString(),
                                  java.nio.charset.StandardCharsets.UTF_8);

                // Write sentinel file to trigger Scilab polling timer
                Files.writeString(Path.of(tmpFilePath + ".ready"), "1");
            }
            event.dropComplete(true);

        } catch (Exception e) {
            event.dropComplete(false);
        }
    }
}
