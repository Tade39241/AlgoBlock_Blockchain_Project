# Add this as a separate file to inspect messages

import sys
import os
import json
import logging

# Configure logging to write to file
logging.basicConfig(
    filename='validator_message_debug.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Monkey patch the syncManager.handleConnection method
from code_node2.Blockchain.Backend.core.network.syncManager import syncManager

original_handle_connection = syncManager.handleConnection

def patched_handle_connection(self):
    try:
        envelope = self.server.read()
        
        # Debug validator selection messages
        if envelope.command == b'valselect':
            logging.debug("===== VALIDATOR SELECTION MESSAGE =====")
            payload = envelope.payload.decode()
            logging.debug(f"Raw payload: {payload}")
            
            try:
                message = json.loads(payload)
                logging.debug(f"Parsed message: {json.dumps(message, indent=2)}")
                
                if "selected_validator" in message:
                    logging.debug(f"Selected validator: {message['selected_validator']}")
                    
                    # Print debug info about blockchain
                    if hasattr(self, 'blockchain'):
                        logging.debug(f"Has blockchain: {self.blockchain is not None}")
                        logging.debug(f"Blockchain has 'needs_genesis': {hasattr(self.blockchain, 'needs_genesis')}")
                        if hasattr(self.blockchain, 'needs_genesis'):
                            logging.debug(f"needs_genesis value: {self.blockchain.needs_genesis}")
            except Exception as e:
                logging.debug(f"Error parsing message: {str(e)}")
    except Exception as e:
        logging.debug(f"Error in patched handler: {str(e)}")
    
    # Call original handler
    return original_handle_connection(self)

# Apply the patch
syncManager.handleConnection = patched_handle_connection