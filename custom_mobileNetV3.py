#%%
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import models
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from torch.optim import SGD, Adam, AdamW
import pymysql
import os
import numpy as np
import torch.nn.functional as F
from torch.hub import load_state_dict_from_url

from PIL import Image
import matplotlib.pyplot as plt

class MobileNetV2(nn.Module):
    def __init__(self, in_channels=6, num_classes=6):
        super(MobileNetV2, self).__init__()
        # Initial convolution layer
        self.conv1 = nn.Conv2d(in_channels, 32, kernel_size=3, stride=2, padding=1)
        self.bn1 = nn.BatchNorm2d(32)
        self.relu1 = nn.ReLU(inplace=True)

        # Inverted residual blocks
        self.block1 = self._make_block(32, 16, stride=1)
        self.block2 = self._make_block(16, 24, stride=2)
        self.block3 = self._make_block(24, 48, stride=2)
        self.block4 = self._make_block(48, 64, stride=2)
        self.block5 = self._make_block(64, 96, stride=1)
        self.block6 = self._make_block(96, 160, stride=2)
        self.block7 = self._make_block(160, 320, stride=2)

        # Final classification layer
        self.conv2 = nn.Conv2d(320, num_classes, kernel_size=1)
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))

    def _make_block(self, in_filters, out_filters, stride=1):
        return nn.Sequential(
            nn.Conv2d(in_filters, out_filters, kernel_size=3, stride=stride, padding=1, bias=False),
            nn.BatchNorm2d(out_filters),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_filters, out_filters, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(out_filters),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        x = self.relu1(self.bn1(self.conv1(x)))
        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)
        x = self.block4(x)
        x = self.block5(x)
        x = self.block6(x)
        x = self.block7(x)
        x = self.avgpool(x)
        x = self.conv2(x)
        x = x.squeeze()
        return x


# Define custom dataset
class CustomDataset(Dataset):
    def __init__(self, images1, images2, labels, transform=None):
        self.images1 = images1
        self.images2 = images2
        self.labels = labels
        self.transform = transform

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        image1 = self.images1[idx]
        image2 = self.images2[idx]
        label = self.labels[idx]
        if self.transform:
            image1 = self.transform(image1)
            image2 = self.transform(image2)
        concatenated_image = torch.cat((image1, image2), dim=0)
        return concatenated_image, label

def data_load(data_path):
    # connect to databse
    connction = pymysql.connect(
        host = "localhost",
        user="root",
        port=3306,
        password="Sam512011",
        database="bw_mismatch_db"
    )

    cursor = connction.cursor()
    # print(bandwidth)
    sql = "SELECT min_bandwidth FROM bw_mismatch_data"
    cursor.execute(sql)
    min_bandwidth = np.array([])
    data = cursor.fetchall()
    all_labels = []
    # for idx, row in enumerate(data):
    #     all_labels.append(row[0])

    # Define paths for images and labels (modify based on your data structure)
    images1_path = os.path.join(data_path, "contour_error")
    images2_path = os.path.join(data_path, "orientation_contour_error")
    # Load image paths (modify based on your file naming convention)
    all_images1 = [os.path.join(images1_path, f) for f in os.listdir(images1_path)]
    all_images2 = [os.path.join(images2_path, f) for f in os.listdir(images2_path)]

    for filename in all_images1:
        id = int(os.path.splitext(os.path.basename(filename))[0])
        sql = "SELECT min_bandwidth FROM bw_mismatch_data WHERE id=%s"
        cursor.execute(sql,(id, ))
        data = cursor.fetchall()
        # print(id, data)
        all_labels.append(data[0][0])
        # print(id, data[0][0])

    # print(all_labels)
    # print(len(all_labels))

    return all_images1, all_images2, all_labels

# Split data and create loaders
def data_split(data_path, split_ratio=0.8, batch_size=32, transform=None):
    # Load your data from 'data_path' here (assuming images and labels are accessible)
    # ...
    all_images1, all_images2, all_labels = data_load(data_path)

    # print(all_images1)


    # Split data into train and test sets
    num_samples = len(all_labels)
    train_size = int(num_samples * split_ratio)
    train_images1, train_images2, train_labels = all_images1[:train_size], all_images2[:train_size], all_labels[:train_size]
    test_images1, test_images2, test_labels = all_images1[train_size:], all_images2[train_size:], all_labels[train_size:]

    # Load and pre-process images (modify based on your needs)
    def load_and_preprocess(image_path):
        # print(image_path)
        image = Image.open(image_path).convert('RGB')  # Ensure RGB format
        if transform is not None:
            pass
            # print('test')
            # image = transform(image)
        return image
    
    train_images1 = [load_and_preprocess(path) for path in train_images1]
    train_images2 = [load_and_preprocess(path) for path in train_images2]
    test_images1 = [load_and_preprocess(path) for path in test_images1]
    test_images2 = [load_and_preprocess(path) for path in test_images2]

    # Create datasets and dataloaders
    train_dataset = CustomDataset(train_images1, train_images2, train_labels, transform=transform)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

    test_dataset = CustomDataset(test_images1, test_images2, test_labels, transform=transform)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    return train_loader, test_loader


# Define transformation (if needed)
transform = transforms.Compose([
    transforms.ToTensor()
    # Add more transforms as needed
])

# Check for GPU availability
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

# Define training parameters
learning_rate = 0.001
num_epochs = 300
batch_size = 256


# Initialize model, loss, optimizer
model = MobileNetV2().to(device)
criterion = nn.CrossEntropyLoss()
# optimizer = optim.Adam(model.parameters(), lr=learning_rate)

data_path = 'C:\\Users\\Samuel\\Desktop\\mismatch_dataset\\'

# Load data
train_loader, test_loader = data_split(data_path,batch_size=batch_size, transform=transform)

progress_bar = []
total_samples = len(train_loader)
n_iterations = np.ceil(total_samples / batch_size)


train_acc = []
test_acc = []
top2_train_acc = []
top2_test_acc = []
loss_epoch_C = []

#%%

param_list=[]
i=0
for param_name,param in model.named_parameters():
    i=i+1
    param_list.append(param_name)
    print(f'layer:{i}_name:{param_name}')

for param_name,param in model.named_parameters():
    if param_name not in param_list[len(param_list)-10:]:
        param.requires_grad=False

# Training loop
for epoch in range(num_epochs):
    model.train()
    running_loss = 0.0
    correct_train, total_train = 0, 0
    correct_test, total_test = 0, 0
    top2_correct_train, top2_correct_test = 0,0
    train_loss_C = 0.0
    

    if epoch == 20:
        learning_rate=0.0005
        for param_name,param in model.named_parameters():
            if param_name in param_list[len(param_list)-10:len(param_list)-2]:
                param.requires_grad=True
    elif epoch ==50:
        learning_rate=0.0002
        for param_name,param in model.named_parameters():
            if param_name in param_list[len(param_list)-31:len(param_list)-10]:
                param.requires_grad=True
    elif epoch ==150:
        for param_name,param in model.named_parameters():
            if param_name in param_list[len(param_list)-58:len(param_list)-31]:
                param.requires_grad=True
    elif epoch ==250:
        for param_name,param in model.named_parameters():
            if param_name in param_list[len(param_list)-88:len(param_list)-58]:
                param.requires_grad=True
    elif epoch ==400:
        for param_name,param in model.named_parameters():
            if param_name in param_list[len(param_list)-106:len(param_list)-88]:
                param.requires_grad=True
    elif epoch ==450:
        learning_rate=0.0001
        for param_name,param in model.named_parameters():
            if param_name in param_list[len(param_list)-136:len(param_list)-106]:
                param.requires_grad=True
    elif epoch ==550:
        for param_name,param in model.named_parameters():
            if param_name in param_list[len(param_list)-161:len(param_list)-136]:
                param.requires_grad=True
                
    parameter=filter(lambda p:p.requires_grad,model.parameters())
    #optimizer=SGD(parameter, lr=lr, momentum=0.9, nesterov = True)
    #optimizer = Adam(parameter, lr=lr,eps=1e-08)
    optimizer_C=AdamW(parameter, lr=learning_rate, amsgrad=True)

    for i, (inputs, labels) in enumerate(train_loader):
        if (i+1) % (total_samples/100) == 0:
            progress_bar.append("=")
            print(f' ||epoch {epoch+1}/{num_epochs}, step {i+1}/{total_samples}',end='\r')

            #print(f'epoch {epoch+1}/{epochs}|',end="")
            for idx, progress in enumerate(progress_bar):
                print(progress,end="")

        inputs, labels = inputs.to(device), labels.to(device)
        optimizer_C.zero_grad()
        outputs = model(inputs)
        # print(outputs, labels)
        # outputs = outputs.squeeze()

        
        
        # print(outputs.shape)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer_C.step()
        running_loss += loss.item()
        _, predicted_top2 = torch.topk(outputs.data, 2, dim=1)
        _, predicted = torch.max(outputs.data, 1)
        total_train += labels.size(0)
        correct_train += (predicted == labels).sum().item()
        top2_correct_train += torch.sum(torch.eq(predicted_top2[:, 0], labels) | torch.eq(predicted_top2[:, 1], labels)).item()

        train_loss_C += loss.item()
    # print(f"Epoch {epoch+1}/{num_epochs}, Loss: {running_loss/len(train_loader)}")
    print(f'Training epoch: {epoch + 1}/{num_epochs} / loss_C: {train_loss_C/len(train_loader)} | acc: {correct_train / total_train} | top 2 acc: {top2_correct_train/total_train}')

    progress_bar = []
                    

    # Testing loop
    model.eval()
  
    with torch.no_grad():
        for i, (inputs, labels) in enumerate(test_loader):
            inputs, labels = inputs.to(device), labels.to(device)
            outputs = model(inputs)
            # outputs = outputs.squeeze()
            _, predicted = torch.max(outputs.data, 1)
            _, predicted_top2 = torch.topk(outputs.data, 2, dim=1)
            total_test += labels.size(0)
            correct_test += (predicted == labels).sum().item()
            top2_correct_test += torch.sum(torch.eq(predicted_top2[:, 0], labels) | torch.eq(predicted_top2[:, 1], labels)).item()

    print(f'Testing acc : {correct_test / total_test} | Top 2 Test acc: {top2_correct_test / total_test}')

    train_acc.append(100 * (correct_train / total_train)) # training accuracy
    test_acc.append(100 * (correct_test / total_test))    # testing accuracy
    loss_epoch_C.append((train_loss_C / len(train_loader)))            # loss 
    top2_train_acc.append(100*(top2_correct_train/total_train)) # training accuracy
    top2_test_acc.append(100*(top2_correct_test / total_test))

# %%

plt.figure()
plt.plot(list(range(num_epochs)), loss_epoch_C) # plot your loss
plt.title('Training Loss')
plt.ylabel('loss'), plt.xlabel('epoch')
plt.legend(['loss_C'], loc = 'upper left')
plt.grid(True)
plt.show()

plt.figure()
plt.plot(list(range(num_epochs)), train_acc)    # plot your training accuracy
plt.plot(list(range(num_epochs)), test_acc)     # plot your testing accuracy
plt.title('Top 1 acc')
plt.ylabel('acc (%)'), plt.xlabel('epoch')
plt.legend(['training acc', 'val acc'], loc = 'upper left')
plt.grid(True)
plt.show()

plt.figure()
plt.plot(list(range(num_epochs)), top2_train_acc)    # plot your training accuracy
plt.plot(list(range(num_epochs)), top2_test_acc)     # plot your testing accuracy
plt.title('Top 2 acc')
plt.ylabel('acc (%)'), plt.xlabel('epoch')
plt.legend(['training acc', 'val acc'], loc = 'upper left')
plt.grid(True)
plt.show()
# %%