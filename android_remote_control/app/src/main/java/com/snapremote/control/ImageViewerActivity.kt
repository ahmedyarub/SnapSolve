package com.snapremote.control

import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import java.io.File

class ImageViewerActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_image_viewer)

        val closeButton: ImageButton = findViewById(R.id.closeButton)
        val imageView: ImageView = findViewById(R.id.responseImageView)

        closeButton.setOnClickListener {
            finish()
        }

        val imagePath = intent.getStringExtra("EXTRA_IMAGE_PATH")
        if (imagePath != null) {
            val file = File(imagePath)
            if (file.exists()) {
                val bitmap = BitmapFactory.decodeFile(file.absolutePath)
                if (bitmap != null) {
                    imageView.setImageBitmap(bitmap)
                } else {
                    Toast.makeText(this, "Failed to decode image", Toast.LENGTH_SHORT).show()
                }
            } else {
                Toast.makeText(this, "Image file not found", Toast.LENGTH_SHORT).show()
            }
        } else {
            Toast.makeText(this, "No image path provided", Toast.LENGTH_SHORT).show()
        }
    }
}
