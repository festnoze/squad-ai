window.safeInterop = {
    callsQueue: [],
    isConnected: false,

    executeOrQueue: function (callback) {
        if (this.isConnected) {
            callback();
        } else {
            this.callsQueue.push(callback);
        }
    },

    executeQueuedCalls: function () {
        this.isConnected = true;
        while (this.callsQueue.length > 0) {
            (this.callsQueue.shift())();
        }
    }
};
